#!/usr/bin/env bash

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_ROOT="$(cd "${SCRIPT_DIR}/.." && pwd)"
VERSION="${1:-1.2.3}"
APP_NAME="DND Campaign Presenter"
APP_BUNDLE_NAME="${APP_NAME}.app"
OUTPUT_ROOT="${PROJECT_ROOT}/packaging/output"
STAGING_DIR="${OUTPUT_ROOT}/macos-dmg"
DMG_NAME="DND-Campaign-Presenter-${VERSION}-macOS.dmg"
DMG_PATH="${OUTPUT_ROOT}/${DMG_NAME}"
VENV_DIR="${PROJECT_ROOT}/.venv-packaging"

if [[ "$(uname -s)" != "Darwin" ]]; then
    echo "This script must be run on macOS." >&2
    exit 1
fi

if ! command -v python3 >/dev/null 2>&1; then
    echo "python3 is required to build the macOS package." >&2
    exit 1
fi

echo "Preparing packaging virtual environment..."
python3 -m venv "${VENV_DIR}"
source "${VENV_DIR}/bin/activate"

python -m pip install --upgrade pip
python -m pip install -r "${PROJECT_ROOT}/requirements.txt" -r "${PROJECT_ROOT}/packaging/requirements-build.txt"

echo "Cleaning previous packaging outputs..."
rm -rf "${PROJECT_ROOT}/build" "${PROJECT_ROOT}/dist" "${STAGING_DIR}" "${DMG_PATH}"
mkdir -p "${OUTPUT_ROOT}"

echo "Building frozen macOS app with PyInstaller..."
export APP_VERSION="${VERSION}"
python -m PyInstaller --clean --noconfirm "${PROJECT_ROOT}/packaging/pyinstaller/dnd_campaign_presenter.spec"

APP_BUNDLE_PATH="${PROJECT_ROOT}/dist/${APP_BUNDLE_NAME}"
if [[ ! -d "${APP_BUNDLE_PATH}" ]]; then
    echo "Expected app bundle not found: ${APP_BUNDLE_PATH}" >&2
    exit 1
fi

echo "Creating DMG staging directory..."
mkdir -p "${STAGING_DIR}"
cp -R "${APP_BUNDLE_PATH}" "${STAGING_DIR}/${APP_BUNDLE_NAME}"
ln -s /Applications "${STAGING_DIR}/Applications"

echo "Creating DMG artifact..."
hdiutil create \
    -volname "${APP_NAME}" \
    -srcfolder "${STAGING_DIR}" \
    -ov \
    -format UDZO \
    "${DMG_PATH}"

rm -rf "${STAGING_DIR}"

echo "macOS package created:"
echo "  ${DMG_PATH}"
