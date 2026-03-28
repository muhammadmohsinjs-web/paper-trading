# Paper Trading

## Run Backend

From the repo root:

```bash
cd backend
./.venv/bin/uvicorn app.main:app --reload --host 0.0.0.0 --port 8000
```

The backend will be available at `http://127.0.0.1:8000`.

VM Server: cd/opt/paper-trading
sudo systemctl restart paper-trading.service
sudo systemctl status paper-trading.service --no-pager -l
