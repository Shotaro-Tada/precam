#!/bin/bash
set -e

echo "============================================================"
echo "  litman v1.0.0 — Installer for Linux"
echo "============================================================"
echo ""

# ── Check prerequisites ──────────────────────────────────────
echo "[1/6] Checking prerequisites..."

if ! command -v git &> /dev/null; then
    echo "  ERROR: Git is not installed."
    echo "  Run: sudo apt install git"
    exit 1
fi
echo "  Git ... OK"

if ! command -v python3 &> /dev/null; then
    echo "  ERROR: Python3 is not installed."
    echo "  Run: sudo apt install python3 python3-pip"
    exit 1
fi
echo "  Python3 ... OK"

if ! python3 -m pip --version &> /dev/null; then
    echo "  ERROR: pip is not available."
    echo "  Run: sudo apt install python3-pip"
    exit 1
fi
echo "  pip ... OK"
echo ""

# ── Git config ───────────────────────────────────────────────
echo "[2/6] Git configuration"
echo ""

read -p "  Your name (e.g. Taro Yamada): " USERNAME
read -p "  Your email: " USEREMAIL

git config --global user.name "$USERNAME"
git config --global user.email "$USEREMAIL"
echo ""
echo "  Git user configured: $USERNAME <$USEREMAIL>"
echo ""

# ── GitHub authentication ────────────────────────────────────
echo "[3/6] GitHub authentication (for shared library access)"
echo ""
echo "  A Personal Access Token (PAT) is required to access"
echo "  the shared library repository (private)."
echo ""
echo "  Open this URL in your browser:"
echo "  https://github.com/settings/tokens/new?scopes=repo&description=litman"
echo ""
echo "  Create a token with 'repo' scope checked."
echo ""
read -sp "  Paste your PAT here (hidden): " PAT
echo ""

git config --global credential.helper store

# Store credential
printf "protocol=https\nhost=github.com\nusername=Shotaro-Tada\npassword=%s\n\n" "$PAT" | git credential approve 2>/dev/null || \
printf "https://Shotaro-Tada:%s@github.com\n" "$PAT" > ~/.git-credentials

echo ""

# ── Verify authentication ────────────────────────────────────
echo "  Verifying authentication..."
if git ls-remote https://github.com/Shotaro-Tada/precam-litman-library.git &> /dev/null; then
    echo "  Authentication ... OK"
else
    echo "  WARNING: Could not access the shared library."
    echo "  Check your PAT and try again later."
    echo "  You can still use litman without sync."
fi
echo ""

# ── Clone repository ─────────────────────────────────────────
echo "[4/6] Cloning repository..."

cd "$HOME"
if [ -d "precam" ]; then
    echo "  precam folder already exists. Pulling latest..."
    git -C precam pull origin main
else
    git clone https://github.com/Shotaro-Tada/precam.git
fi
echo ""

# ── Install dependencies ─────────────────────────────────────
echo "[5/6] Installing dependencies..."

cd "$HOME/precam/litman"
python3 -m pip install -e . 2>/dev/null || python3 -m pip install --user -e .
echo "  Dependencies installed."
echo ""

# ── Create launcher with book icon ──────────────────────────
echo "[6/6] Creating desktop launcher..."

mkdir -p "$HOME/precam/litman/assets"

# Generate book icon using Pillow (installed with streamlit)
python3 -c "
from PIL import Image, ImageDraw
img = Image.new('RGBA', (256, 256), (0, 0, 0, 0))
d = ImageDraw.Draw(img)
d.rounded_rectangle([30,20,226,236], radius=12, fill='#1565C0', outline='#0D47A1', width=4)
d.rectangle([50,30,216,226], fill='#FAFAFA', outline='#E0E0E0', width=2)
for y in range(60, 200, 22):
    d.line([(65,y),(200,y)], fill='#BDBDBD', width=2)
d.line([(50,20),(50,236)], fill='#0D47A1', width=6)
d.polygon([(180,20),(195,20),(195,70),(187,58),(180,70)], fill='#E53935')
img.save('$HOME/precam/litman/assets/book.png', format='PNG')
"

# Create launch script (auto-detect location, conda init for desktop launch)
cat > "$HOME/precam/litman/litman.sh" << 'LAUNCH'
#!/bin/bash
SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
if [ -f "$HOME/anaconda3/etc/profile.d/conda.sh" ]; then
    source "$HOME/anaconda3/etc/profile.d/conda.sh"
    conda activate base
elif [ -f "$HOME/miniconda3/etc/profile.d/conda.sh" ]; then
    source "$HOME/miniconda3/etc/profile.d/conda.sh"
    conda activate base
else
    source ~/.bashrc 2>/dev/null
fi
cd "$SCRIPT_DIR"
python3 -m streamlit run src/litman/gui.py
if [ $? -ne 0 ]; then
    echo ""
    echo "Error: streamlit failed to start."
    echo "Press Enter to close..."
    read
fi
LAUNCH
chmod +x "$HOME/precam/litman/litman.sh"

# Create .desktop launcher on Desktop
DESKTOP_DIR="$HOME/Desktop"
if [ ! -d "$DESKTOP_DIR" ]; then
    DESKTOP_DIR=$(xdg-user-dir DESKTOP 2>/dev/null || echo "$HOME/Desktop")
fi
mkdir -p "$DESKTOP_DIR"

cat > "$DESKTOP_DIR/litman.desktop" << DESKTOP
[Desktop Entry]
Version=1.0
Type=Application
Name=litman
Comment=Literature Manager
Exec=bash $HOME/precam/litman/litman.sh
Icon=$HOME/precam/litman/assets/book.png
Terminal=true
Categories=Science;Education;
DESKTOP
chmod +x "$DESKTOP_DIR/litman.desktop"

echo "  Desktop launcher created: litman.desktop (book icon)"
echo ""

# ── Done ─────────────────────────────────────────────────────
echo "============================================================"
echo "  Installation complete!"
echo "============================================================"
echo ""
echo "  To launch litman:"
echo "    Double-click the 'litman' icon on your Desktop"
echo "    Browser will open automatically at http://localhost:8501"
echo ""
echo "  Or from terminal:"
echo "    bash ~/precam/litman/litman.sh"
echo ""
echo "  First time: Go to Sync page and click 'Pull from GitHub'"
echo ""
