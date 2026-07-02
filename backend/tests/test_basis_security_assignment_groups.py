from app.services.dashboard_assignment_groups import is_basis_security_assignment_group


def test_basis_security_assignment_group_classifier_matches_confirmed_examples() -> None:
    basis_security_groups = [
        "IT-SAP-Global-Basis",
        "IT-SAP-MEU-Security",
        "IT-SAP-AMEA-Security",
        "IT-SAP-NA-Security",
        "IT-NSA-Global-Security",
        "IT-SAP-LA-Security",
        "IT-SAP-RU-MDLZ-SECURITY",
        "IT-SAP-Russia-Basis",
        "IT-NSA-Global-Security360",
        "IT-NSA-LA-Security",
        "IT-NSA-NA-MTI-Security-AccessControl",
        "IT-SAP-Chipita-Basis",
        "  it-sap-global-basis  ",
        "IT-SAP\u00a0Global\u00a0Security",
    ]
    for assignment_group in basis_security_groups:
        assert is_basis_security_assignment_group(assignment_group)


def test_basis_security_assignment_group_classifier_ignores_non_matches() -> None:
    assert not is_basis_security_assignment_group("IT-NSA-NA-STC-SALESFORCE-PerfectStore")
    assert not is_basis_security_assignment_group("General Service Request")
    assert not is_basis_security_assignment_group("")
    assert not is_basis_security_assignment_group("   ")
    assert not is_basis_security_assignment_group(None)
