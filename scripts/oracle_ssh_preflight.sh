#!/usr/bin/env bash
# Preflight de acceso SSH a Oracle para los workflows.
#
# Solo lectura: no modifica la VM remota y NUNCA imprime el contenido de
# ORACLE_SSH_KEY. Reporta, con un código de salida distinto por causa, cuál de
# los tres secretos falta o por qué no autentica.
#
# Uso:
#   scripts/oracle_ssh_preflight.sh [--connect] [--host-only] [--any-host-key]
#
#   --connect       además intenta un login real (`id -un`) para distinguir
#                   "huella correcta pero clave no autorizada".
#   --host-only     solo valida ORACLE_HOST y la clave pública del servidor
#                   (para workflows que no usan ORACLE_USER/ORACLE_SSH_KEY).
#   --any-host-key  no compara contra la huella fijada; solo la informa.
#
# Códigos de salida:
#   0  acceso correcto
#   2  falta uno o más secretos del entorno oracle-production
#   3  ORACLE_SSH_KEY no es una clave privada usable
#   4  el host no resuelve o no responde en el puerto SSH
#   5  la huella del servidor no coincide con la fijada
#   6  la clave no autentica para ese usuario
#   7  otro fallo de SSH
set -uo pipefail

EXPECTED_FINGERPRINT_DEFAULT='SHA256:UDVMx6HCL8d412N+TaY4O0Ob1rGVTWI6vKmz0Dm3yyY'
EXPECTED_FINGERPRINT="$EXPECTED_FINGERPRINT_DEFAULT"
MODE_CONNECT=0
MODE_HOST_ONLY=0
COMPARE_FINGERPRINT=1

for arg in "$@"; do
  case "$arg" in
    --connect) MODE_CONNECT=1 ;;
    --host-only) MODE_HOST_ONLY=1 ;;
    --any-host-key) COMPARE_FINGERPRINT=0 ;;
    --expected-fingerprint=*) EXPECTED_FINGERPRINT="${arg#*=}" ;;
    -h|--help) sed -n '2,24p' "$0"; exit 0 ;;
    *) echo "::error::Argumento desconocido: $arg"; exit 7 ;;
  esac
done

# La clave nunca entra en un `set -x` ni en la salida: cualquier traza del
# runner imprimiría el valor expandido.
set +x

HOST="${ORACLE_HOST:-}"
USER_NAME="${ORACLE_USER:-}"
SSH_KEY="${ORACLE_SSH_KEY:-}"

workdir="$(mktemp -d)"
chmod 700 "$workdir"
keyfile="$workdir/id_oracle"
knownfile="$workdir/known_hosts"
trap 'rm -rf "$workdir"' EXIT

summary() {
  [ -n "${GITHUB_STEP_SUMMARY:-}" ] || return 0
  printf '%s\n' "$*" >> "$GITHUB_STEP_SUMMARY"
}

fail() { # fail <exit-code> <mensaje>
  local code="$1"; shift
  printf '::error::%s\n' "$*"
  echo "ORACLE_SSH_PREFLIGHT=failed code=$code"
  summary "### Acceso SSH a Oracle: **falló** (código $code)"
  summary ""
  summary "$*"
  exit "$code"
}

# --- 1. Secretos: nombrar exactamente cuál falta ----------------------------
missing=()
[ -n "$HOST" ] || missing+=("ORACLE_HOST")
if [ "$MODE_HOST_ONLY" -eq 0 ]; then
  [ -n "$USER_NAME" ] || missing+=("ORACLE_USER")
  [ -n "$SSH_KEY" ] || missing+=("ORACLE_SSH_KEY")
fi

if [ ${#missing[@]} -gt 0 ]; then
  for name in "${missing[@]}"; do
    case "$name" in
      ORACLE_HOST)
        echo "::error title=Secreto faltante::$name está vacío en el entorno oracle-production. Debe ser la IP pública de la VM (144.22.213.171)." ;;
      ORACLE_USER)
        echo "::error title=Secreto faltante::$name está vacío en el entorno oracle-production. En imágenes Ubuntu es 'ubuntu'; en Oracle Linux es 'opc'." ;;
      ORACLE_SSH_KEY)
        echo "::error title=Secreto faltante::$name está vacío en el entorno oracle-production. Debe ser la clave privada completa, con sus líneas BEGIN/END." ;;
    esac
  done
  echo "ORACLE_SSH_PREFLIGHT=failed code=2 missing=${missing[*]}"
  summary "### Acceso SSH a Oracle: **falta configurar**"
  summary ""
  summary "Cargá en Settings → Environments → oracle-production → Environment secrets: \`${missing[*]}\`."
  exit 2
fi

case "$HOST" in
  *[!a-zA-Z0-9.:-]*) fail 7 "ORACLE_HOST contiene caracteres inválidos para un host o IP: '$HOST'" ;;
esac
[ "$MODE_HOST_ONLY" -eq 1 ] || case "$USER_NAME" in
  *[!a-zA-Z0-9._-]*) fail 7 "ORACLE_USER contiene caracteres inválidos: '$USER_NAME'" ;;
esac

# --- 2. Formato de la clave privada ----------------------------------------
if [ "$MODE_HOST_ONLY" -eq 0 ]; then
  if ! printf '%s' "$SSH_KEY" | grep -q 'PRIVATE KEY'; then
    fail 3 "ORACLE_SSH_KEY no contiene un encabezado 'PRIVATE KEY': se guardó truncada, sin las líneas BEGIN/END, o se pegó solo la clave pública."
  fi
  printf '%s\n' "$SSH_KEY" > "$keyfile"
  chmod 600 "$keyfile"
  if ! ssh-keygen -y -f "$keyfile" </dev/null >/dev/null 2>&1; then
    fail 3 "ORACLE_SSH_KEY no se puede leer como clave privada OpenSSH: puede tener passphrase (el runner no puede desbloquearla), estar en formato PEM antiguo o tener líneas partidas por el copiado."
  fi
fi

# --- 3. Identidad pública del servidor -------------------------------------
if ! ssh-keyscan -T 10 -t ed25519 "$HOST" >"$knownfile" 2>/dev/null || [ ! -s "$knownfile" ]; then
  fail 4 "SSH no respondió en $HOST:22: revisá ORACLE_HOST, que la instancia esté Running en OCI y que la security list permita el puerto 22. (Los valores de los otros secretos no se tocaron.)"
fi

actual="$(ssh-keygen -lf "$knownfile" -E sha256 | awk '{print $2}' | head -1)"
echo "ORACLE_HOST=$HOST"
echo "ORACLE_HOST_KEY_ED25519=$actual"

if [ "$COMPARE_FINGERPRINT" -eq 1 ] && [ "$actual" != "$EXPECTED_FINGERPRINT" ]; then
  fail 5 "La huella de $HOST es $actual y la fijada en los workflows es $EXPECTED_FINGERPRINT. Es otra máquina (o se regeneraron las host keys): no se intentó autenticar y no se modificó nada."
fi

# --- 4. Autenticación real (opcional) --------------------------------------
if [ "$MODE_HOST_ONLY" -eq 0 ] && [ "$MODE_CONNECT" -eq 1 ]; then
  output="$(ssh -i "$keyfile" \
      -o IdentitiesOnly=yes -o BatchMode=yes -o PasswordAuthentication=no \
      -o StrictHostKeyChecking=yes -o UserKnownHostsFile="$knownfile" \
      -o ConnectTimeout=15 -o ConnectionAttempts=1 \
      "$USER_NAME@$HOST" 'printf "SSH_LOGIN_OK\n"; id -un' 2>&1)"
  rc=$?
  if [ "$rc" -ne 0 ]; then
    echo "$output" | sed -e 's/^/ssh: /'
    case "$output" in
      *"Permission denied"*)
        fail 6 "SSH respondió pero rechazó la clave para $USER_NAME@$HOST: ORACLE_SSH_KEY no está en authorized_keys de ese usuario, o ORACLE_USER no es el correcto (ubuntu en imágenes Ubuntu, opc en Oracle Linux). La huella del servidor sí es la esperada." ;;
      *"Host key verification failed"*)
        fail 5 "La verificación de la host key falló al conectar, aunque el keyscan coincidió: revisá que no haya un known_hosts previo en el runner." ;;
      *"Connection timed out"*|*"Connection refused"*|*"No route to host"*)
        fail 4 "No se pudo abrir la conexión con $HOST:22 (timeout o rechazo)." ;;
      *"Too many authentication failures"*)
        fail 6 "sshd cortó por demasiados intentos de clave: verificá que ORACLE_SSH_KEY sea la única clave ofrecida (IdentitiesOnly ya está activo) y que el usuario exista." ;;
      *"kex_exchange_identification"*|*"banner exchange"*)
        fail 7 "sshd aceptó el TCP pero cortó el intercambio (posible fail2ban o límite de conexiones). Esperá unos minutos y reintentá." ;;
      *)
        fail 7 "ssh terminó con código $rc para $USER_NAME@$HOST. Última línea: $(printf '%s' "$output" | tail -1)" ;;
    esac
  fi
  login_user="$(printf '%s\n' "$output" | sed -n '2p')"
  echo "ORACLE_SSH_AUTH_USER=$login_user"
  summary "### Acceso SSH a Oracle: **correcto**"
  summary ""
  summary "- Host: \`$HOST\` (huella esperada)"
  summary "- Usuario: \`$USER_NAME\` → inicia sesión como \`$login_user\`"
  echo "ORACLE_SSH_PREFLIGHT=ok code=0"
  exit 0
fi

echo "ORACLE_SSH_PREFLIGHT=ok code=0 auth=not_tested"
summary "### Acceso SSH a Oracle: **huella y secretos correctos**"
summary ""
summary "No se intentó login (modo sin \`--connect\`)."
exit 0
