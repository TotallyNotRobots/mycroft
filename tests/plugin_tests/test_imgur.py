import responses
from responses import RequestsMock

from plugins import imgur


def test_imgur_no_api(mock_requests: RequestsMock, mock_api_keys):
    mock_api_keys.config.get_api_key.return_value = None
    imgur.set_api()
    response = imgur.imgur("aries")

    assert response == "No imgur API details"


def test_imgur(mock_requests: RequestsMock, mock_api_keys):
    mock_requests.add(
        responses.GET,
        "https://api.imgur.com/3/credits",
        json={},
    )
    mock_requests.add(
        responses.GET,
        "https://api.imgur.com/3/gallery/search/time/all/4?q=foobar",
        json={},
    )
    imgur.set_api()
    response = imgur.imgur("foobar")

    assert response == "No imgur API details"
