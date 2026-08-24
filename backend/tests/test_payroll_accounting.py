from decimal import Decimal

from sqlalchemy import select

from app.accounting_models import Account, JournalEntry, JournalLine
from app.db import SessionLocal


def test_payroll_approval_posts_expense_net_and_withholdings_once(client, owner_headers) -> None:
    me = client.get('/me', headers=owner_headers).json()
    employee = client.post(
        '/hr/employees',
        headers=owner_headers,
        json={
            'branch_id': me['branch_id'],
            'employee_code': 'PAY-ACC-001',
            'full_name': 'Empleado Contable',
            'position': 'Ventas',
            'department': 'Comercial',
            'hire_date': '2026-08-01',
            'base_salary': '1000.00',
        },
    )
    assert employee.status_code == 201, employee.text

    run = client.post(
        '/payroll/runs',
        headers=owner_headers,
        json={
            'period_key': 'payroll-accounting-test',
            'period_start': '2026-08-01',
            'period_end': '2026-08-15',
        },
    )
    assert run.status_code == 201, run.text
    run_id = run.json()['id']

    line = client.post(
        f'/payroll/runs/{run_id}/lines',
        headers=owner_headers,
        json={
            'employee_id': employee.json()['id'],
            'gross': '500.00',
            'bonuses': '50.00',
            'deductions': '25.00',
            'note': 'quincena',
        },
    )
    assert line.status_code == 201, line.text
    assert line.json()['net'] == '525.00'

    first = client.post(f'/payroll/runs/{run_id}/approve', headers=owner_headers)
    assert first.status_code == 200, first.text
    repeated = client.post(f'/payroll/runs/{run_id}/approve', headers=owner_headers)
    assert repeated.status_code == 200, repeated.text

    with SessionLocal() as db:
        entries = db.scalars(
            select(JournalEntry).where(JournalEntry.reference == f'PAYROLL:{run_id}')
        ).all()
        assert len(entries) == 1
        entry = entries[0]
        assert entry.status == 'posted'
        rows = db.execute(
            select(Account.code, JournalLine.debit, JournalLine.credit)
            .join(JournalLine, JournalLine.account_id == Account.id)
            .where(JournalLine.journal_entry_id == entry.id)
        ).all()
        by_code = {code: (Decimal(debit), Decimal(credit)) for code, debit, credit in rows}
        assert by_code['5100'] == (Decimal('550.00'), Decimal('0.00'))
        assert by_code['2100'] == (Decimal('0.00'), Decimal('525.00'))
        assert by_code['2110'] == (Decimal('0.00'), Decimal('25.00'))
