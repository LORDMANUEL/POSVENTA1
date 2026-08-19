def test_platform_admin_can_create_second_tenant_and_login_by_slug(client, owner_headers) -> None:
    me = client.get('/me', headers=owner_headers)
    assert me.status_code == 200
    first_branch_id = me.json()['branch_id']

    access = client.get('/platform/access', headers=owner_headers)
    assert access.status_code == 200
    assert access.json()['platform_admin'] is True

    created = client.post(
        '/platform/tenants',
        headers=owner_headers,
        json={
            'store_name': 'Mily Zebra SPS',
            'store_slug': 'mily-zebra-sps',
            'branch_name': 'San Pedro Sula',
            'branch_code': 'SPS-01',
            # Deliberately reuse the email from the first tenant: tenant scope must
            # make this valid and force explicit tenant selection on ambiguous login.
            'owner_email': 'owner@example.com',
            'owner_full_name': 'Owner SPS',
            'owner_password': 'second-tenant-secure-password',
        },
    )
    assert created.status_code == 201, created.text
    second = created.json()
    assert second['tenant']['slug'] == 'mily-zebra-sps'
    assert second['owner']['platform_admin'] is False
    assert second['admin_login_path'] == '/admin?tenant=mily-zebra-sps'

    ambiguous = client.post(
        '/auth/login',
        data={'username': 'owner@example.com', 'password': 'super-secure-password'},
    )
    assert ambiguous.status_code == 409

    login = client.post(
        '/auth/login',
        data={
            'username': 'mily-zebra-sps:owner@example.com',
            'password': 'second-tenant-secure-password',
        },
    )
    assert login.status_code == 200, login.text
    second_headers = {'Authorization': f"Bearer {login.json()['access_token']}"}
    second_me = client.get('/me', headers=second_headers)
    assert second_me.status_code == 200
    assert second_me.json()['tenant_id'] == second['tenant']['id']

    second_access = client.get('/platform/access', headers=second_headers)
    assert second_access.status_code == 200
    assert second_access.json()['platform_admin'] is False

    forbidden_platform = client.post(
        '/platform/tenants',
        headers=second_headers,
        json={
            'store_name': 'No Permitida',
            'store_slug': 'no-permitida',
            'branch_name': 'Principal',
            'branch_code': 'NO-01',
            'owner_email': 'third@example.com',
            'owner_full_name': 'Third',
            'owner_password': 'third-tenant-secure-password',
        },
    )
    assert forbidden_platform.status_code == 403

    product = client.post(
        '/products',
        headers=second_headers,
        json={
            'sku': 'TENANT-2-001',
            'name': 'Producto tenant dos',
            'unit_cost': '10.00',
            'sale_price': '25.00',
        },
    )
    assert product.status_code == 201

    cross_tenant_branch = client.post(
        '/inventory/movements',
        headers=second_headers,
        json={
            'product_id': product.json()['id'],
            'branch_id': first_branch_id,
            'quantity_delta': '1',
            'reason': 'cross_tenant_probe',
        },
    )
    assert cross_tenant_branch.status_code == 404


def test_platform_admin_lists_tenants_without_exposing_owner_secrets(client, owner_headers) -> None:
    response = client.get('/platform/tenants', headers=owner_headers)
    assert response.status_code == 200
    assert len(response.json()) == 1
    row = response.json()[0]
    assert row['slug'] == 'mily-zebra'
    assert 'password_hash' not in row
    assert 'bootstrap_token' not in row
