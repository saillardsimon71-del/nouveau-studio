def test_avatar_demo_prepares_a_real_render_without_starting_gpu(client):
    response = client.post("/api/projects/avatar-demo")
    assert response.status_code == 201
    project = response.json()
    assert project["format"] == "9:16"
    shot = project["shots"][0]
    assert shot["kind"] == "avatar"
    assert shot["duration_s"] == 3.72
    assert shot["params"]["engine_hint"] == "modal_avatar"
    assert shot["character"]["base_image"].startswith("art_")
    assert project["cost"]["jobs"] == 0
