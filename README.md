# rsync-backup

A Python-based backup utility using `rsync` with a configurable grace period before deleting files that have been removed from the source.

## Features

- Incremental backups using `rsync -av`
- Delayed deletion via `--grace-days` / `GRACE_DAYS` (default: 14) — files deleted from the source are retained in the destination until the grace period expires
- Automatically cancels scheduled deletion if a file reappears in the source
- Dry-run support (`--dry-run` or `DRY_RUN=1`) to preview changes safely
- Concurrency protection via file locking to prevent overlapping runs
- Logging to both stdout and dated log files in `/var/log/rsync_backup/`
- Persistent state tracking in `/var/lib/rsync_backup/`

## Installation

```bash
git clone <repository-url>
cd rsync-backup
sudo cp rsync-backup.py /usr/local/sbin/rsync-backup
sudo chmod +x /usr/local/sbin/rsync-backup
sudo mkdir -p /var/log/rsync_backup /var/lib/rsync_backup
sudo chown root:root /var/log/rsync_backup /var/lib/rsync_backup
sudo chmod 750 /var/log/rsync_backup /var/lib/rsync_backup
```

## Usage

```bash
rsync-backup <source_directory> <destination_directory>
```

### Example

```bash
rsync-backup /home/user/data /backup/data
```

### Options

| Option            | Environment variable | Default | Description                                      |
|-------------------|----------------------|---------|--------------------------------------------------|
| `--grace-days N`  | `GRACE_DAYS`         | 14      | Days a file must remain missing before deletion  |
| `--dry-run`       | `DRY_RUN=1`          | off     | Preview changes without modifying anything       |

```bash
# Preview with a longer grace period
rsync-backup --grace-days 30 --dry-run /home/user/data /backup/data

# Same thing using environment variables
GRACE_DAYS=30 DRY_RUN=1 rsync-backup /home/user/data /backup/data
```

## Cron Setup

Run nightly at 02:00 (edit with `sudo crontab -e`):

```
0 2 * * * /usr/local/sbin/rsync-backup /home/user/data /backup/data
```

## Logging & State

| Type  | Location                                      |
|-------|-----------------------------------------------|
| Logs  | `/var/log/rsync_backup/<pair>-YYYY-MM-DD_HH-MM-SS.log` |
| State | `/var/lib/rsync_backup/<pair>.missing.tsv`    |
| Lock  | `/var/lib/rsync_backup/<pair>.lock`           |

`<pair>` is derived from the source and destination paths (e.g. `home_user_data-to-backup_data`).

## How Delayed Deletion Works

Instead of running `rsync --delete` immediately, missing paths are tracked in the state file:

1. **Day 1** — File disappears from source → recorded as missing, kept in destination
2. **Days 2–13** — Still missing → kept in destination  
   (if it reappears in the source, it is removed from the deletion queue)
3. **Day 14+** — Missing for at least `GRACE_DAYS` → deleted from destination

## Requirements

- Python 3.8+
- `rsync`
- Linux (uses `fcntl` for locking)
```
