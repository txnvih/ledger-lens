from api.index import app

client = app.test_client()
response = client.get("/api/reconcile")

print(response.json)