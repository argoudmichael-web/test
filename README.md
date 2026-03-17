# Maintenance PC

Scripts de maintenance automatique pour garder votre PC en bonne santé.

## Contenu

| Fichier | OS | Description |
|---|---|---|
| `maintenance-pc.sh` | Linux | Script Bash de maintenance complète |
| `maintenance-pc.ps1` | Windows | Script PowerShell de maintenance complète |

## Fonctionnalités

Les deux scripts effectuent les opérations suivantes :

1. **Mise à jour système** - Paquets système, applications
2. **Nettoyage** - Fichiers temporaires, cache, journaux
3. **Espace disque** - Vérification et alertes
4. **Santé des disques** - Vérification SMART / état physique
5. **Mémoire RAM** - Utilisation actuelle
6. **Services / Démarrage** - Vérification des services critiques
7. **Sécurité** - Pare-feu, antivirus, mises à jour de sécurité
8. **Redémarrage** - Indication si un redémarrage est nécessaire

## Utilisation

### Linux

```bash
sudo bash maintenance-pc.sh
```

### Windows

Ouvrir PowerShell **en tant qu'Administrateur**, puis :

```powershell
.\maintenance-pc.ps1
```

## Planification automatique

### Linux (cron) - Exécution hebdomadaire

```bash
sudo crontab -e
# Ajouter la ligne suivante (chaque dimanche à 3h du matin) :
0 3 * * 0 /chemin/vers/maintenance-pc.sh >> /var/log/maintenance-pc.log 2>&1
```

### Windows (Planificateur de tâches)

```powershell
$action = New-ScheduledTaskAction -Execute "PowerShell.exe" -Argument "-File C:\chemin\vers\maintenance-pc.ps1"
$trigger = New-ScheduledTaskTrigger -Weekly -DaysOfWeek Sunday -At 3am
Register-ScheduledTask -Action $action -Trigger $trigger -TaskName "MaintenancePC" -RunLevel Highest
```
