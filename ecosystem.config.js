module.exports = {
  apps: [{
    name: 'mining-bot',
    cwd: '/home/ubuntu/mining-bot',
    script: '/home/ubuntu/mining-bot/run.py',
    interpreter: '/usr/bin/python3',
    args: 'config.json',
    instances: 1,
    exec_mode: 'fork',
    watch: false,
    max_restarts: 10,
    restart_delay: 5000,
    autorestart: true,
    log_date_format: 'YYYY-MM-DD HH:mm:ss Z',
    error_file: '/home/ubuntu/mining-bot/logs/err.log',
    out_file: '/home/ubuntu/mining-bot/logs/out.log',
    merge_logs: true,
    env: {
      PYTHONUNBUFFERED: '1',
    },
  }]
};