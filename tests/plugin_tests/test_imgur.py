import random

import responses
from responses import RequestsMock

from plugins import imgur


def test_imgur_no_api(mock_requests: RequestsMock, mock_api_keys):
    mock_api_keys.config.get_api_key.return_value = None
    imgur.set_api()
    response = imgur.imgur("aries")

    assert response == "No imgur API details"


def test_imgur_no_results(mock_requests: RequestsMock, mock_api_keys):
    random.seed(0)
    mock_requests.add(
        responses.GET,
        "https://api.imgur.com/3/credits",
        json={},
    )

    mock_requests.add(
        responses.GET,
        "https://api.imgur.com/3/gallery/search/time/all/4?q=foobar",
        json=[],
    )

    imgur.set_api()
    response = imgur.imgur("foobar")

    assert response == "No results found."


def test_imgur_meme(mock_requests: RequestsMock, mock_api_keys):
    random.seed(0)
    mock_requests.add(
        responses.GET,
        "https://api.imgur.com/3/credits",
        json={},
    )

    mock_requests.add(
        responses.GET,
        "https://api.imgur.com/3/gallery/search/time/all/4?q=foobar",
        json=[
            {
                "is_album": False,
                "title": "foo",
                "meme_metadata": {
                    "meme_name": "foo",
                },
                "section": "",
                "nsfw": True,
                "link": "foo.bar",
            },
            {
                "is_album": True,
                "title": "bar",
                "section": "section",
                "nsfw": False,
                "link": "bar.baz",
            },
            {
                "is_album": False,
                "title": "",
                "section": "",
                "nsfw": True,
                "link": "foo.invalid",
            },
        ],
    )

    imgur.set_api()
    response = imgur.imgur("foobar")

    assert response == '[\2nsfw\2] "\2foo\2 - foo" - foo.bar'
