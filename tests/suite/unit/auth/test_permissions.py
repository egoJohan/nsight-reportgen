"""Who may see what.

This is the security-critical file: with nSight holding a tenant-wide datahive
token, these functions are the only thing separating one customer's data from
another's. Every case below is a customer-visible failure if it regresses.
"""
from reportbuilder.auth.permissions import Grant, User, may_read, may_write, visible_scopes


def user(*grants, admin=False):
    return User(id="u1", email="a@b.c", name="A", is_admin=admin,
                grants=tuple(Grant(s, m) for s, m in grants))


class TestCustomerGrant:
    def test_reaches_the_customer_itself(self):
        u = user(("attendo", "edit"))
        assert may_read(u, "attendo/customer.json")

    def test_reaches_the_cases_under_it(self):
        u = user(("attendo", "edit"))
        assert may_read(u, "attendo/case-9b32/report/rep-1")

    def test_does_not_reach_another_customer(self):
        u = user(("attendo", "edit"))
        assert not may_read(u, "synsam/customer.json")

    def test_does_not_match_a_customer_by_prefix(self):
        """"attendo" must not admit "attendo-oy" — a path prefix is a path
        prefix, not a string prefix."""
        u = user(("attendo", "edit"))
        assert not may_read(u, "attendo-oy/customer.json")


class TestCaseGrant:
    def test_reaches_its_own_case(self):
        u = user(("attendo/case-9b32", "edit"))
        assert may_read(u, "attendo/case-9b32/report/rep-1")

    def test_does_not_reach_the_customer_above_it(self):
        """Speksi 2 P-O-06/07: access to one study WITHOUT its customer."""
        u = user(("attendo/case-9b32", "edit"))
        assert not may_read(u, "attendo/customer.json")

    def test_does_not_reach_a_sibling_case(self):
        u = user(("attendo/case-9b32", "edit"))
        assert not may_read(u, "attendo/case-0000/report/rep-1")


class TestMode:
    def test_view_can_read(self):
        assert may_read(user(("attendo", "view")), "attendo/customer.json")

    def test_view_cannot_write(self):
        assert not may_write(user(("attendo", "view")), "attendo/customer.json")

    def test_edit_can_write(self):
        assert may_write(user(("attendo", "edit")), "attendo/customer.json")

    def test_the_most_specific_grant_decides(self):
        """A view grant on one case does not override edit on the customer, and
        an edit grant on one case does not leak edit to its siblings."""
        u = user(("attendo", "view"), ("attendo/case-9b32", "edit"))
        assert may_write(u, "attendo/case-9b32/report/rep-1")
        assert not may_write(u, "attendo/case-0000/report/rep-1")


class TestAdmin:
    def test_admin_is_not_access(self):
        """Administering access and having access are different things. An admin
        with no grant sees no data."""
        u = user(admin=True)
        assert not may_read(u, "attendo/customer.json")
        assert not may_write(u, "attendo/customer.json")

    def test_admin_with_a_grant_is_ordinary(self):
        u = user(("attendo", "view"), admin=True)
        assert may_read(u, "attendo/customer.json")
        assert not may_write(u, "attendo/customer.json")


class TestSettingsPaths:
    def test_nobody_reaches_settings_by_grant(self):
        """`settings/**` holds users, grants and app configuration. It is
        reached by the admin dependency, never by a data grant — otherwise a
        grant named "settings" would be privilege escalation."""
        u = user(("settings", "edit"))
        assert not may_read(u, "settings/user/u2")
        assert not may_write(u, "settings/access.json")


class TestVisibleScopes:
    def test_lists_what_a_user_may_see(self):
        u = user(("attendo", "edit"), ("synsam/case-1", "view"))
        assert visible_scopes(u) == ("attendo", "synsam/case-1")

    def test_no_grants_is_empty_not_everything(self):
        assert visible_scopes(user()) == ()


class TestMalformedGrants:
    def test_empty_scope_is_rejected(self):
        """An empty scope is a tenant-wide wildcard. Reviewer's repro:
        Grant('', 'edit') -> may_read(u, 'attendo/customer.json') == True
        Grant('', 'edit') -> may_read(u, 'synsam/case-1/report/rep-1') == True
        This must raise, not silently breach."""
        try:
            Grant("", "edit")
            assert False, "Grant('', 'edit') should raise ValueError"
        except ValueError:
            pass

    def test_scope_with_trailing_slash_is_rejected(self):
        """Global constraints: never a trailing slash."""
        try:
            Grant("attendo/", "edit")
            assert False, "Grant with trailing slash should raise ValueError"
        except ValueError:
            pass

    def test_scope_with_dot_segment_is_rejected(self):
        """Defence in depth: reject . segments in scope."""
        try:
            Grant("attendo/./case-9b32", "edit")
            assert False, "Grant with . segment should raise ValueError"
        except ValueError:
            pass

    def test_scope_with_dotdot_segment_is_rejected(self):
        """Defence in depth: reject .. segments in scope."""
        try:
            Grant("attendo/..", "edit")
            assert False, "Grant with .. segment should raise ValueError"
        except ValueError:
            pass

    def test_invalid_mode_view_is_rejected(self):
        """Mode must be exactly 'view' or 'edit', case-sensitive."""
        try:
            Grant("attendo", "View")
            assert False, "Grant with invalid mode 'View' should raise ValueError"
        except ValueError:
            pass

    def test_invalid_mode_is_rejected(self):
        """Mode must be exactly 'view' or 'edit'."""
        try:
            Grant("attendo", "admin")
            assert False, "Grant with invalid mode 'admin' should raise ValueError"
        except ValueError:
            pass


class TestMalformedPaths:
    def test_path_with_dotdot_traversal_is_not_covered(self):
        """Reviewer's repro: Grant('attendo/case-9b32','edit') must not cover
        'attendo/case-9b32/../../synsam/customer.json'. While _seg() in
        store/paths.py rejects this today, covers() must defend in depth and
        return False for any path with . or .. segments."""
        g = Grant("attendo/case-9b32", "edit")
        assert not g.covers("attendo/case-9b32/../../synsam/customer.json")

    def test_path_with_dot_segment_is_not_covered(self):
        """Defence in depth: a path with . segments is not covered."""
        g = Grant("attendo", "edit")
        assert not g.covers("attendo/./case-9b32/report")

    def test_path_with_dotdot_segment_is_not_covered(self):
        """Defence in depth: a path with .. segments is not covered."""
        g = Grant("attendo", "edit")
        assert not g.covers("attendo/case-9b32/../case-0000/report")
