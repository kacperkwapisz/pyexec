from unittest.mock import patch, MagicMock


def test_health_check(client):
    """Tests that the health check endpoint is available and working."""
    response = client.get("/health")
    assert response.status_code == 200
    assert response.json() == {"status": "ok"}


def test_unauthorized_access(client):
    """Tests that an invalid API key is correctly rejected."""
    response = client.post(
        "/execute",
        headers={"X-API-Key": "this-is-a-wrong-key"},
        json={"session_id": "any-session", "code": "print('hello')"},
    )
    assert response.status_code == 403


def test_install_queues_background_task(client, test_session):
    """Tests that the /install endpoint correctly queues a background task."""
    with patch("pyexec.main.do_install") as mock_do_install:
        response = client.post(
            "/install",
            json={"session_id": test_session, "packages": ["requests"]},
        )
        assert response.status_code == 202
        data = response.json()
        assert data["status"] == "install_queued"
        mock_do_install.assert_called_once_with(test_session, ["requests"])


def test_execute_queues_background_task(client, test_session):
    """Tests that the /execute endpoint correctly queues a background task."""
    code_to_run = "print('hello world')"
    with patch("pyexec.main.do_execute") as mock_do_execute:
        response = client.post(
            "/execute",
            json={"session_id": test_session, "code": code_to_run, "env": {}},
        )
        assert response.status_code == 202
        data = response.json()
        assert data["status"] == "execute_queued"
        mock_do_execute.assert_called_once_with(
            test_session, code_to_run, {}, data["task_id"]
        )


def test_terminate_deletes_session_dir(client, test_session):
    """Tests that the /terminate endpoint correctly deletes the session directory."""
    from pyexec.config import settings

    session_path = settings.BASE_SESSION_PATH / test_session
    assert session_path.exists()

    response = client.post("/terminate", json={"session_id": test_session})
    assert response.status_code == 200
    assert not session_path.exists()

    # Also test that terminating a non-existent session is handled gracefully
    response = client.post("/terminate", json={"session_id": "non-existent-session"})
    assert response.status_code == 200  # The endpoint is idempotent
    assert "not found" in response.json()["message"]


# --- Tests for background task logic ---


def test_do_install_creates_venv_and_installs(test_session, mock_docker_globally):
    """
    Tests the logic of the do_install background task, ensuring it
    creates a virtual environment and then installs packages into it.
    """
    from pyexec.main import do_install
    from pyexec.config import settings

    mock_docker_globally.containers.run.reset_mock()
    packages = ["numpy", "pandas"]
    session_path = settings.BASE_SESSION_PATH / test_session
    venv_python_path = str(session_path / "venv" / "bin" / "python")

    # Simulate that the venv does *not* exist to test the creation path
    with patch("pathlib.Path.exists", return_value=False):
        do_install(test_session, packages)

        assert mock_docker_globally.containers.run.call_count == 2

        # Call 1: Create the virtual environment
        create_venv_call = mock_docker_globally.containers.run.call_args_list[0]
        assert create_venv_call.kwargs["command"] == ["python", "-m", "venv", "venv"]
        assert str(session_path) in create_venv_call.kwargs["volumes"]

        # Call 2: Install packages using the new venv's pip
        pip_install_call = mock_docker_globally.containers.run.call_args_list[1]
        assert (
            pip_install_call.kwargs["command"]
            == [
                venv_python_path,
                "-m",
                "pip",
                "install",
            ]
            + packages
        )


def test_do_execute_uses_venv_or_falls_back(test_session, mock_docker_globally):
    """
    Tests the logic of the do_execute background task, ensuring it uses the
    session's virtual environment if it exists, and falls back otherwise.
    """
    from pyexec.main import do_execute, get_session_venv_path
    from pyexec.config import settings

    mock_docker_globally.containers.run.reset_mock()
    session_path = settings.BASE_SESSION_PATH / test_session
    venv_python_path = get_session_venv_path(session_path)
    code, task_key = "print(1)", "exec-123"

    # Case 1: Venv exists, so it should be used
    with patch("pathlib.Path.exists", return_value=True):
        do_execute(test_session, code, {}, task_key)
        run_call = mock_docker_globally.containers.run.call_args
        assert run_call.kwargs["command"][0] == str(venv_python_path)

    # Case 2: Venv does not exist, so it should fall back to the global python
    with patch("pathlib.Path.exists", return_value=False):
        do_execute(test_session, code, {}, task_key)
        run_call = mock_docker_globally.containers.run.call_args
        assert run_call.kwargs["command"][0] == "python"
