# Google OIDC — activación de IAchat

La implementación usa el flujo oficial **OpenID Connect Authorization Code + PKCE** de Google. Valida firma RS256 mediante JWKS, issuer, audience, expiración, state, nonce y \`sub\`. La identidad persistente se asocia exclusivamente al \`sub\` verificado, nunca al email; no fusiona ni borra cuentas existentes.

## Única configuración externa pendiente

1. Crear en [Google Cloud Console](https://console.cloud.google.com/apis/credentials) un **OAuth client ID** de tipo **Aplicación web** y configurar la pantalla de consentimiento. Para compartir IAchat con otras cuentas, publicar/configurar el consentimiento de Google según corresponda.
2. Agregar la URI autorizada de redirección **exacta**: \`https://DOMINIO-DE-IACHAT/auth/google/callback\`. Usar el dominio público HTTPS real de IAchat (no el de G.O.).
3. En la VM Oracle, crear \`/etc/iachat/google-oidc.env\` (root:root, 0600) con:
   \`\`\`ini
   IACHAT_GOOGLE_CLIENT_ID=CLIENT_ID
   IACHAT_GOOGLE_CLIENT_SECRET=CLIENT_SECRET
   IACHAT_PUBLIC_ORIGIN=https://DOMINIO-DE-IACHAT
   \`\`\`
   No copiar esos valores a chats, repositorios ni logs. Son obligatorios para iniciar sesión: el deploy valida ambos archivos y los carga por systemd; tras instalar credenciales en una VM ya desplegada, reiniciar solamente \`iachat.service\`.
4. La clave de firma de sesión \`IACHAT_AUTH_SECRET\` **no** se configura a mano: el despliegue la crea una sola vez en \`/etc/iachat/auth.env\` (root:root, 0600) y la carga por systemd. Si ya existe, se conserva: rotarla cierra todas las sesiones abiertas. Sin ella no se puede iniciar sesión por ningún método.
5. \`GET /auth/status\` debe indicar \`google_enabled: true\`. El botón **Continuar con Google** aparecerá en la pantalla de inicio. Probar una sesión real con consentimiento y una segunda sesión del mismo usuario; no confundir la prueba simulada de OIDC con un login real.

Si faltan credenciales, Google permanece deshabilitado de forma explícita y el sitio queda sin acceso: el login por contraseña sólo sirve como recuperación cuando ya existe una cuenta y \`IACHAT_PASSWORD\` está definido, y también necesita \`IACHAT_AUTH_SECRET\` para emitir la cookie de sesión. La autenticación anterior con contraseña queda disponible para recuperación, sin borrar datos. Las cuentas Google se crean automáticamente y sus historiales/archivos permanecen separados por usuario.
