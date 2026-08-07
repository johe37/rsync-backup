# rsync-backup

A simple Bash-based backup utility using `rsync`.

The script performs scheduled backups from a source directory to a destination directory, creates separate dated log files for each backup run, and is designed to be executed automatically using `cron`.

## Features

* Uses `rsync` for efficient incremental backups
* Accepts source and destination directories as arguments
* Creates a unique log file for each backup run
* Stores logs in `/var/log/rsync_backup/`
* Preserves file attributes using rsync archive mode
* Prevents destination data from drifting using `--delete`
* Suitable for nightly cron backups

## Installation

Clone the repository:

```bash
git clone <repository-url>
cd rsync-backup
```

Install the script:

```bash
sudo cp backup-rsync.sh /usr/local/sbin/backup-rsync.sh
sudo chmod +x /usr/local/sbin/backup-rsync.sh
```

Create the log directory:

```bash
sudo mkdir -p /var/log/rsync_backup
sudo chown root:root /var/log/rsync_backup
sudo chmod 750 /var/log/rsync_backup
```

## Usage

Run manually:

```bash
backup-rsync.sh <source_directory> <destination_directory>
```

Example:

```bash
backup-rsync.sh /home/user/data /backup/data
```

This will create a log file similar to:

```text
/var/log/rsync_backup/home_user_data-to-backup_data-2026-08-07.log
```

## Cron Setup

To run the backup every night at 02:00:

Edit the root crontab:

```bash
sudo crontab -e
```

Add:

```cron
0 2 * * * /usr/local/sbin/backup-rsync.sh /home/user/data /backup/data
```

The backup will now run automatically every night.

## Logging

Each execution creates a new log file:

```text
/var/log/rsync_backup/
├── home_user_data-to-backup_data-2026-08-07.log
├── home_user_data-to-backup_data-2026-08-08.log
└── home_user_data-to-backup_data-2026-08-09.log
```

Logs contain:

* Backup start time
* Source and destination paths
* rsync output
* Success or failure status

## Log Rotation

Because logs are stored under `/var/log`, it is recommended to configure `logrotate`.

Create:

```bash
sudo nano /etc/logrotate.d/rsync_backup
```

Add:

```conf
/var/log/rsync_backup/*.log {
    weekly
    rotate 12
    compress
    missingok
    notifempty
}
```

This keeps approximately three months of logs.

## Important Notes

### `--delete`

The script uses:

```bash
rsync --delete
```

This means files deleted from the source will also be removed from the backup destination.

Example:

```
Source:
  file1.txt
  file2.txt

Delete file2.txt from source

Next backup:
  file2.txt is removed from destination
```

If you need historical recovery, use snapshots or remove `--delete`.

## Requirements

* Linux system
* Bash
* rsync
* cron

Install rsync if needed:

Debian/Ubuntu:

```bash
sudo apt install rsync
```

RHEL/Fedora:

```bash
sudo dnf install rsync
```

## License

MIT License

