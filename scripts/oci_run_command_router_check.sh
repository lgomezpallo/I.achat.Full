#!/bin/bash
# Verificación de solo lectura de Router, pensada para pegarse tal cual en
# OCI → Compute → Instancia → Oracle Cloud Agent → Run command.
#
# No escribe nada, no reinicia servicios y no imprime credenciales: de
# /etc/iachat/router.env solo muestra nombres de variables y si el token está
# definido, nunca su valor.
#
# Uso: pegar el contenido completo en Run command (se ejecuta como root).
# Salida: líneas CLAVE=valor, más un resumen final.

set -u

echo "ROUTER_CHECK_MODE=read_only"
echo "HOSTNAME=$(hostname 2>/dev/null || echo unknown)"
echo "WHOAMI=$(id -un 2>/dev/null || echo unknown)"
if [ -r /etc/os-release ]; then
  # shellcheck disable=SC1091
  . /etc/os-release
  echo "OS=$PRETTY_NAME"
fi

# --- router.service ---------------------------------------------------------
echo "ROUTER_UNIT_LOAD=$(systemctl show router -p LoadState --value 2>/dev/null || echo unknown)"
echo "ROUTER_UNIT_ACTIVE=$(systemctl is-active router 2>/dev/null || echo unknown)"
echo "ROUTER_UNIT_ENABLED=$(systemctl is-enabled router 2>/dev/null || echo unknown)"
echo "ROUTER_UNIT_SUBSTATE=$(systemctl show router -p SubState --value 2>/dev/null || echo unknown)"
echo "ROUTER_UNIT_SINCE=$(systemctl show router -p ActiveEnterTimestamp --value 2>/dev/null || echo unknown)"
echo "ROUTER_UNIT_EXIT=$(systemctl show router -p ExecMainStatus --value 2>/dev/null || echo unknown)"
echo "ROUTER_UNIT_RESTARTS=$(systemctl show router -p NRestarts --value 2>/dev/null || echo unknown)"
echo "ROUTER_UNIT_WORKDIR=$(systemctl show router -p WorkingDirectory --value 2>/dev/null || echo unknown)"

# --- puerto 8010 ------------------------------------------------------------
if command -v ss >/dev/null 2>&1; then
  listening="$(ss -ltnH 2>/dev/null | awk '$4 ~ /:8010$/')"
  echo "PORT_8010_LISTEN=$([ -n "$listening" ] && echo 1 || echo 0)"
  echo "PORT_8010_BIND=$(printf '%s\n' "$listening" | awk '{print $4}' | paste -sd, -)"
  echo "PORT_8010_NON_LOOPBACK=$(printf '%s\n' "$listening" | awk '$4 !~ /^(127\.0\.0\.1|\[::1\]):8010$/ {found=1} END {print found+0}')"
  echo "PORT_8010_PROCESS=$(ss -ltnpH 2>/dev/null | awk '$4 ~ /:8010$/ {print $6}' | paste -sd, -)"
else
  echo "PORT_8010_LISTEN=unknown (no está ss)"
fi

# --- health ----------------------------------------------------------------
if command -v curl >/dev/null 2>&1; then
  echo "ROUTER_HEALTH_HTTP=$(curl -s -o /dev/null -w '%{http_code}' --max-time 5 http://127.0.0.1:8010/health 2>/dev/null || echo 000)"
  echo "ROUTER_ROOT_HTTP=$(curl -s -o /dev/null -w '%{http_code}' --max-time 5 http://127.0.0.1:8010/ 2>/dev/null || echo 000)"
  echo "IACHAT_READY_HTTP=$(curl -s -o /dev/null -w '%{http_code}' --max-time 5 http://127.0.0.1:8000/ready 2>/dev/null || echo 000)"
  echo "IACHAT_READY_MODE=$(curl -fsS --max-time 5 http://127.0.0.1:8000/ready 2>/dev/null | sed -n 's/.*"mode":"\([a-z]*\)".*/\1/p' || true)"
  echo "IACHAT_HEALTH_HTTP=$(curl -s -o /dev/null -w '%{http_code}' --max-time 5 http://127.0.0.1:8000/health 2>/dev/null || echo 000)"
else
  echo "ROUTER_HEALTH_HTTP=unknown (no está curl)"
fi

# --- IAchat usa Router ------------------------------------------------------
echo "IACHAT_UNIT_ACTIVE=$(systemctl is-active iachat 2>/dev/null || echo unknown)"

# --- configuración de IAchat para Router: solo metadatos -------------------
envfile=/etc/iachat/router.env
if [ -e "$envfile" ]; then
  echo "IACHAT_ROUTER_ENV=present"
  echo "IACHAT_ROUTER_ENV_MODE=$(stat -c '%a' "$envfile" 2>/dev/null || echo unknown)"
  echo "IACHAT_ROUTER_ENV_OWNER=$(stat -c '%U:%G' "$envfile" 2>/dev/null || echo unknown)"
  # Nombres de variables: nunca los valores.
  echo "IACHAT_ROUTER_ENV_KEYS=$(grep -oE '^[[:space:]]*(export[[:space:]]+)?[A-Za-z_][A-Za-z0-9_]*' "$envfile" 2>/dev/null | sed 's/^[[:space:]]*//; s/^export[[:space:]]*//' | paste -sd, -)"
  if grep -qE '^[[:space:]]*(export[[:space:]]+)?ROUTER_TOKEN=[^[:space:]]' "$envfile" 2>/dev/null; then
    echo "IACHAT_ROUTER_TOKEN_SET=1"
  else
    echo "IACHAT_ROUTER_TOKEN_SET=0"
  fi
  if grep -qE '^[[:space:]]*(export[[:space:]]+)?ROUTER_URL=http://(127\.0\.0\.1|localhost):8010' "$envfile" 2>/dev/null; then
    echo "IACHAT_ROUTER_URL_LOOPBACK=1"
  else
    echo "IACHAT_ROUTER_URL_LOOPBACK=0"
  fi
else
  echo "IACHAT_ROUTER_ENV=absent"
fi

# --- resumen ----------------------------------------------------------------
active="$(systemctl is-active router 2>/dev/null || true)"
listen="$(ss -ltnH 2>/dev/null | awk '$4 ~ /:8010$/ {found=1} END {print found+0}')"
health="$(curl -s -o /dev/null -w '%{http_code}' --max-time 5 http://127.0.0.1:8010/health 2>/dev/null || true)"
if [ "$active" = "active" ] && [ "${listen:-0}" = "1" ] && [ "$health" = "200" ]; then
  echo "ROUTER_READONLY_SUMMARY=ok"
else
  echo "ROUTER_READONLY_SUMMARY=problems unit=$active listen=${listen:-0} health=${health:-000}"
fi
echo "ROUTER_CHECK_COMPLETE=read_only_no_writes"
