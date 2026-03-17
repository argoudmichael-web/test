#!/bin/bash
# =============================================================================
# Script de maintenance PC - Linux
# =============================================================================
# Usage: sudo bash maintenance-pc.sh
# =============================================================================

set -euo pipefail

RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m'

section() {
    echo ""
    echo -e "${BLUE}══════════════════════════════════════════════${NC}"
    echo -e "${BLUE}  $1${NC}"
    echo -e "${BLUE}══════════════════════════════════════════════${NC}"
}

success() { echo -e "${GREEN}[OK]${NC} $1"; }
warn()    { echo -e "${YELLOW}[!]${NC} $1"; }
error()   { echo -e "${RED}[X]${NC} $1"; }

# Vérifier les droits root
if [ "$EUID" -ne 0 ]; then
    error "Ce script doit être exécuté en tant que root (sudo)"
    exit 1
fi

echo -e "${GREEN}"
echo "  __  __       _       _                                   ____   ____ "
echo " |  \/  | __ _(_)_ __ | |_ ___ _ __   __ _ _ __   ___ ___|  _ \ / ___|"
echo " | |\/| |/ _\` | | '_ \| __/ _ \ '_ \ / _\` | '_ \ / __/ _ \ |_) | |    "
echo " | |  | | (_| | | | | | ||  __/ | | | (_| | | | | (_|  __/  __/| |___ "
echo " |_|  |_|\__,_|_|_| |_|\__\___|_| |_|\__,_|_| |_|\___\___|_|    \____|"
echo -e "${NC}"
echo "  Date: $(date '+%Y-%m-%d %H:%M:%S')"
echo ""

# ─── 1. Mise à jour des paquets système ───
section "1. Mise à jour des paquets système"

if command -v apt &>/dev/null; then
    echo "Gestionnaire détecté: APT (Debian/Ubuntu)"
    apt update -y
    apt upgrade -y
    apt dist-upgrade -y
    apt autoremove -y
    apt autoclean -y
    success "Paquets APT mis à jour"
elif command -v dnf &>/dev/null; then
    echo "Gestionnaire détecté: DNF (Fedora/RHEL)"
    dnf upgrade --refresh -y
    dnf autoremove -y
    success "Paquets DNF mis à jour"
elif command -v pacman &>/dev/null; then
    echo "Gestionnaire détecté: Pacman (Arch)"
    pacman -Syu --noconfirm
    success "Paquets Pacman mis à jour"
else
    warn "Gestionnaire de paquets non reconnu"
fi

# ─── 2. Mise à jour des pilotes ───
section "2. Mise à jour des pilotes"

if command -v ubuntu-drivers &>/dev/null; then
    echo "Outil ubuntu-drivers détecté"
    ubuntu-drivers autoinstall
    success "Pilotes recommandés installés"
elif command -v apt &>/dev/null; then
    apt install --fix-missing -y linux-firmware 2>/dev/null || true
    success "Firmware Linux mis à jour"
elif command -v dnf &>/dev/null; then
    dnf update --refresh -y linux-firmware kernel-modules 2>/dev/null || true
    success "Pilotes/firmware mis à jour (DNF)"
elif command -v pacman &>/dev/null; then
    pacman -S --noconfirm linux-firmware 2>/dev/null || true
    success "Pilotes/firmware mis à jour (Pacman)"
else
    warn "Aucun outil de gestion de pilotes détecté"
fi

# ─── 3. Mise à jour Snap ───
section "3. Mise à jour des paquets Snap"

if command -v snap &>/dev/null; then
    snap refresh
    success "Paquets Snap mis à jour"
else
    warn "Snap n'est pas installé"
fi

# ─── 4. Mise à jour Flatpak ───
section "4. Mise à jour des paquets Flatpak"

if command -v flatpak &>/dev/null; then
    flatpak update -y
    flatpak uninstall --unused -y
    success "Paquets Flatpak mis à jour"
else
    warn "Flatpak n'est pas installé"
fi

# ─── 5. Nettoyage du cache ───
section "5. Nettoyage du cache et fichiers temporaires"

FREED=0

# Cache APT
if [ -d /var/cache/apt/archives ]; then
    BEFORE=$(du -s /var/cache/apt/archives 2>/dev/null | awk '{print $1}')
    apt clean 2>/dev/null || true
    AFTER=$(du -s /var/cache/apt/archives 2>/dev/null | awk '{print $1}')
    FREED=$((FREED + BEFORE - AFTER))
fi

# Fichiers temporaires
if [ -d /tmp ]; then
    find /tmp -type f -atime +7 -delete 2>/dev/null || true
    success "Fichiers temporaires de plus de 7 jours supprimés"
fi

# Journaux anciens
if command -v journalctl &>/dev/null; then
    journalctl --vacuum-time=7d 2>/dev/null
    success "Journaux système nettoyés (> 7 jours)"
fi

# Anciens noyaux (Debian/Ubuntu)
if command -v apt &>/dev/null; then
    apt autoremove --purge -y 2>/dev/null || true
    success "Anciens noyaux supprimés"
fi

success "Nettoyage terminé"

# ─── 6. Vérification de l'espace disque ───
section "6. Espace disque"

df -h / /home 2>/dev/null | while read -r line; do
    echo "  $line"
done

USAGE=$(df / | tail -1 | awk '{print $5}' | tr -d '%')
if [ "$USAGE" -gt 90 ]; then
    error "Espace disque critique: ${USAGE}% utilisé sur /"
elif [ "$USAGE" -gt 75 ]; then
    warn "Espace disque élevé: ${USAGE}% utilisé sur /"
else
    success "Espace disque OK: ${USAGE}% utilisé sur /"
fi

# ─── 7. Vérification de la mémoire ───
section "7. Mémoire RAM"

free -h | while read -r line; do
    echo "  $line"
done

# ─── 8. Vérification de la santé des disques ───
section "8. Santé des disques (SMART)"

if command -v smartctl &>/dev/null; then
    for disk in /dev/sd? /dev/nvme?n?; do
        if [ -b "$disk" ]; then
            STATUS=$(smartctl -H "$disk" 2>/dev/null | grep -i "result\|status" | head -1)
            if echo "$STATUS" | grep -qi "passed\|ok"; then
                success "$disk: $STATUS"
            else
                warn "$disk: $STATUS"
            fi
        fi
    done
else
    warn "smartmontools non installé (installer avec: apt install smartmontools)"
fi

# ─── 9. Vérification des services ───
section "9. Services système"

for service in ssh ufw fail2ban cron; do
    if systemctl is-active --quiet "$service" 2>/dev/null; then
        success "$service: actif"
    elif systemctl is-enabled --quiet "$service" 2>/dev/null; then
        warn "$service: activé mais non démarré"
    else
        echo "  $service: non installé/désactivé"
    fi
done

# ─── 10. Vérification de la sécurité ───
section "10. Vérifications de sécurité"

# Vérifier le pare-feu
if command -v ufw &>/dev/null; then
    UFW_STATUS=$(ufw status | head -1)
    if echo "$UFW_STATUS" | grep -qi "active"; then
        success "Pare-feu UFW: actif"
    else
        warn "Pare-feu UFW: inactif - pensez à l'activer (ufw enable)"
    fi
fi

# Vérifier les mises à jour de sécurité en attente
if command -v apt &>/dev/null; then
    SECURITY_UPDATES=$(apt list --upgradable 2>/dev/null | grep -c "security" || true)
    if [ "$SECURITY_UPDATES" -gt 0 ]; then
        warn "$SECURITY_UPDATES mises à jour de sécurité en attente"
    else
        success "Aucune mise à jour de sécurité en attente"
    fi
fi

# ─── 11. Vérification du redémarrage ───
section "11. Redémarrage nécessaire ?"

if [ -f /var/run/reboot-required ]; then
    warn "Un redémarrage est nécessaire pour appliquer les mises à jour"
    if [ -f /var/run/reboot-required.pkgs ]; then
        echo "  Paquets nécessitant un redémarrage:"
        cat /var/run/reboot-required.pkgs | while read -r pkg; do
            echo "    - $pkg"
        done
    fi
else
    success "Aucun redémarrage nécessaire"
fi

# ─── Résumé ───
section "Maintenance terminée"
echo ""
echo "  Date de fin: $(date '+%Y-%m-%d %H:%M:%S')"
echo ""
success "Votre PC est à jour et en bonne santé !"
echo ""
