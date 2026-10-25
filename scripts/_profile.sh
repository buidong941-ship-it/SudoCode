# Dùng chung cho các script bash: nạp profiles/$RUN_PROFILE.env (rồi .env) vào môi trường, KHÔNG ghi đè biến đã đặt —
# cùng thứ tự ưu tiên với core/config.py: biến môi trường thật > profile > .env.
#   source scripts/_profile.sh
_load_env_file() {
  [ -f "$1" ] || return 0
  while IFS= read -r line || [ -n "$line" ]; do
    line="${line%$'\r'}"
    case "$line" in ''|\#*) continue ;; esac
    case "$line" in *=*) ;; *) continue ;; esac
    k="${line%%=*}"; v="${line#*=}"
    k="$(echo "$k" | tr -d '[:space:]')"
    v="${v%\"}"; v="${v#\"}"; v="${v%\'}"; v="${v#\'}"
    if [ -z "${!k+x}" ]; then export "$k=$v"; fi
  done < "$1"
}
if [ -n "${RUN_PROFILE:-}" ]; then
  [ -f "profiles/$RUN_PROFILE.env" ] || { echo "không có profiles/$RUN_PROFILE.env" >&2; exit 1; }
  _load_env_file "profiles/$RUN_PROFILE.env"
fi
_load_env_file ".env"
