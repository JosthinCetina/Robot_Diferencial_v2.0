#!/usr/bin/env bash
set -euo pipefail

VISIBILITY="${1:-public}"
REPO_NAME="dif_bot_os_jazzy"

if [[ "$VISIBILITY" != "public" && "$VISIBILITY" != "private" ]]; then
  echo "Uso: ./scripts/publish_github.sh [public|private]" >&2
  exit 2
fi

if [[ ! -f Dockerfile || ! -d src || ! -d web ]]; then
  echo "Ejecuta este script desde la raíz del proyecto dif_bot_os_jazzy." >&2
  exit 2
fi

command -v git >/dev/null || { echo "Git no está instalado." >&2; exit 1; }
command -v gh >/dev/null || { echo "Instala GitHub CLI (gh) antes de continuar: https://cli.github.com/" >&2; exit 1; }
gh auth status >/dev/null

if [[ ! -d .git ]]; then
  git init --initial-branch=main
fi

if git remote get-url origin >/dev/null 2>&1; then
  echo "Ya existe un remote 'origin'. No lo sobrescribo automáticamente." >&2
  git remote -v
  exit 1
fi

git add -A
if ! git diff --cached --quiet; then
  git commit -m "dif_bot OS v2.0 - ROS 2 Jazzy and Gazebo Harmonic"
fi

gh repo create "$REPO_NAME" --source . --remote origin --push "--$VISIBILITY"
echo "Repositorio publicado: $(git remote get-url origin)"
echo "Visibilidad: $VISIBILITY"
