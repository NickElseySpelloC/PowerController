# Data API (WIP)

```bash
curl -X 'GET' http://192.168.86.47:8081/outputs \
    -H 'accept: application/json' 
    -H 'Authorization: Bearer abc123'

curl -H "X-Access-Key: abc123" http://localhost:8081/all

curl -H "Authorization: Bearer abc123" \
    -H 'accept: application/json' \
    http://localhost:8081/all 



curl "http://localhost:8081/all?access_key=abc123"

```