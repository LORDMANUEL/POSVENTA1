def test_current_cash_recovers_open_session_and_clears_after_close(client, owner_headers) -> None:
    initial = client.get('/cash/current', headers=owner_headers)
    assert initial.status_code == 200
    assert initial.json() is None

    opened = client.post('/cash/open', headers=owner_headers, json={'opening_amount': '75.00'})
    assert opened.status_code == 201
    session_id = opened.json()['id']

    current = client.get('/cash/current', headers=owner_headers)
    assert current.status_code == 200
    assert current.json()['id'] == session_id
    assert current.json()['opening_amount'] == '75.00'
    assert current.json()['expected_amount'] == '75.00'

    closed = client.post(
        f'/cash/{session_id}/close',
        headers=owner_headers,
        json={'closing_amount': '75.00'},
    )
    assert closed.status_code == 200
    assert closed.json()['difference'] == '0.00'

    after = client.get('/cash/current', headers=owner_headers)
    assert after.status_code == 200
    assert after.json() is None
