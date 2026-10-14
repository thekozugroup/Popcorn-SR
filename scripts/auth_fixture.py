"""Password authentication for isolated acceptance fixtures, never user deployments."""


def sign_in(client, password):
    response = client.post("/api/login", json={"username": "admin", "password": password})
    if response.status_code == 401:
        client.post("/api/login", json={"username": "admin", "password": "admin"}).raise_for_status()
        client.post(
            "/api/account/password", json={"username": "admin", "password": password}
        ).raise_for_status()
    else:
        response.raise_for_status()
    client.post("/api/auth/passkeys/skip").raise_for_status()
