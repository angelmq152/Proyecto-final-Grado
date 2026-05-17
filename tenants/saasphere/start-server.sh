#!/bin/bash
# Inicia nginx en un contenedor ligero (bwrap) en puerto 8081
# Para ver la web: http://localhost:8081

JOBDIR="/home/angel/.claude/jobs/45eb0da5"
NGINX="$JOBDIR/nginx-pkg/nginx-extracted/usr/sbin/nginx"
CONF="$JOBDIR/nginx-userspace.conf"

PID_FILE="$JOBDIR/nginx-run/nginx.pid"

if [ -f "$PID_FILE" ] && kill -0 "$(cat $PID_FILE)" 2>/dev/null; then
  echo "nginx ya está corriendo (PID=$(cat $PID_FILE))"
  echo "  → http://localhost:8081"
  exit 0
fi

mkdir -p "$JOBDIR/nginx-run/"{logs,temp/{client,proxy,fastcgi,uwsgi,scgi}}

setsid nohup bwrap \
  --ro-bind / / \
  --proc /proc \
  --dev /dev \
  --tmpfs /tmp \
  --bind /home/angel/futuraweb /home/angel/futuraweb \
  --bind "$JOBDIR/nginx-run" "$JOBDIR/nginx-run" \
  --bind "$JOBDIR/nginx-pkg" "$JOBDIR/nginx-pkg" \
  --share-net \
  "$NGINX" -c "$CONF" \
  </dev/null >"$JOBDIR/nginx-run/logs/bwrap.log" 2>&1 &
disown

sleep 1
if curl -s -o /dev/null -w "%{http_code}" http://localhost:8081/ | grep -q "200"; then
  echo "✓ nginx corriendo en http://localhost:8081"
else
  echo "✗ Error al iniciar nginx. Ver log: $JOBDIR/nginx-run/logs/error.log"
fi
