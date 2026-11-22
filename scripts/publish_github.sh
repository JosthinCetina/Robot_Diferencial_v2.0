#!/usr/bin/env bash
set -Eeuo pipefail

EXPECTED_REPO="JosthinCetina/Robot_Diferencial_v2.0"
EXPECTED_HTTPS="https://github.com/JosthinCetina/Robot_Diferencial_v2.0.git"
EXPECTED_SSH="git@github.com:JosthinCetina/Robot_Diferencial_v2.0.git"
DRY_RUN=false

if [[ "${1:-}" == "--dry-run" ]]; then
  DRY_RUN=true
elif [[ $# -gt 0 ]]; then
  echo "Uso: ./scripts/publish_github.sh [--dry-run]" >&2
  exit 2
fi

fail() {
  echo "[ERROR] $*" >&2
  exit 1
}

command -v git >/dev/null 2>&1 || fail "Git no está instalado."
command -v gh >/dev/null 2>&1 || fail "GitHub CLI (gh) no está instalado."
gh auth status >/dev/null 2>&1 || fail "Autentica GitHub CLI con 'gh auth login'."

ROOT="$(git rev-parse --show-toplevel 2>/dev/null)" || fail "Ejecuta el script dentro del repositorio."
cd "$ROOT"

[[ "$(git branch --show-current)" == "main" ]] || fail "La rama actual debe ser main."
[[ -f Dockerfile && -d src && -d web ]] || fail "No parece ser la raíz de DIF_BOT OS."

REMOTE="$(git remote get-url origin 2>/dev/null || true)"
if [[ -z "$REMOTE" ]]; then
  gh repo view "$EXPECTED_REPO" >/dev/null 2>&1 || fail "No se encontró el repositorio existente $EXPECTED_REPO."
  git remote add origin "$EXPECTED_HTTPS"
  REMOTE="$EXPECTED_HTTPS"
fi

case "$REMOTE" in
  "$EXPECTED_HTTPS"|https://github.com/JosthinCetina/Robot_Diferencial_v2.0|"$EXPECTED_SSH"|git@github.com:JosthinCetina/Robot_Diferencial_v2.0)
    ;;
  *)
    fail "El remote origin apunta a otro repositorio: $REMOTE"
    ;;
esac

echo "[1/5] Sincronizando referencias de GitHub..."
git fetch origin main

if ! git merge-base --is-ancestor origin/main HEAD; then
  fail "La copia local no contiene el último historial de origin/main. Sincroniza antes de publicar; no se hará ningún reset."
fi

echo "[2/5] Preparando cambios respetando .gitignore..."
git add -A
git diff --cached --check

if git diff --cached --quiet; then
  echo "No hay cambios nuevos para publicar."
  exit 0
fi

echo
echo "Cambios que se publicarían:"
git diff --cached --stat
git diff --cached --name-only
echo

if [[ "$DRY_RUN" == "true" ]]; then
  echo "[DRY-RUN] No se creó commit ni se publicó nada."
  exit 0
fi

echo "[3/5] Creando commit..."
git commit -m "Update DIF_BOT OS implementation"

echo "[4/5] Publicando en el repositorio existente..."
git push origin main

echo "[5/5] Verificando sincronización..."
git fetch origin main
[[ "$(git rev-parse HEAD)" == "$(git rev-parse origin/main)" ]] || fail "El push terminó, pero HEAD y origin/main no coinciden."

echo
echo "=========================================="
echo " PUBLICACIÓN COMPLETADA"
echo "=========================================="
git log -1 --oneline
git status --short
