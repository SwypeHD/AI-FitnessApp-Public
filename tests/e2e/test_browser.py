"""Browser-based end-to-end tests using Playwright.

Starts a real uvicorn server with a temp data dir and drives a headless Chromium
browser through the full UI: navigate pages, log food via the quick-log bar,
verify slot rendering, delete and move items, and assert the DOM reflects correct
slot assignments at every step.
"""

from __future__ import annotations

import socket
import threading
import time

import pytest
import uvicorn
from playwright.sync_api import Page, expect

from fitness.config.composition import Container
from fitness.config.settings import Settings
from fitness.web.app import create_app
from fitness.web.dependencies import get_container


def _free_port() -> int:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
        s.bind(("127.0.0.1", 0))
        return s.getsockname()[1]


@pytest.fixture
def live_server(tmp_path):
    """Start a real HTTP server backed by a fresh temp data directory per test."""
    settings = Settings(data_dir=str(tmp_path))
    container = Container(settings)

    app = create_app()
    app.dependency_overrides[get_container] = lambda: container

    port = _free_port()
    config = uvicorn.Config(app, host="127.0.0.1", port=port, log_level="error")
    server = uvicorn.Server(config)
    thread = threading.Thread(target=server.run, daemon=True)
    thread.start()

    deadline = time.monotonic() + 10
    while not server.started and time.monotonic() < deadline:
        time.sleep(0.05)
    assert server.started, "uvicorn did not start within 10s"

    yield f"http://127.0.0.1:{port}"

    server.should_exit = True
    thread.join(timeout=5)
    app.dependency_overrides.clear()


@pytest.fixture
def food_page(live_server: str, page: Page):
    """Navigate to the Food Log page and wait for it to be visible."""
    page.goto(f"{live_server}/static/index.html")
    page.click('nav a[data-page="food"]')
    page.wait_for_selector("#page-food.active")
    return page


def ai_send(page: Page, text: str):
    """Type into the AI panel input and submit, waiting for the refresh to complete."""
    inp = page.locator("#aiInput")
    inp.fill(text)
    with page.expect_response(lambda r: "/messages" in r.url):
        page.locator("#aiForm button[type='submit']").click()
    page.wait_for_timeout(500)


def slot_food_names(page: Page, slot: str) -> list[str]:
    """Return food names displayed under a given slot header in the food log."""
    slots = page.locator("#foodSlots .log-slot")
    count = slots.count()
    for i in range(count):
        s = slots.nth(i)
        header = s.locator(".slot-header h3").text_content().strip().lower()
        if header == slot:
            names = s.locator(".food-name")
            return [names.nth(j).text_content().strip() for j in range(names.count())]
    return []


def slot_has_empty(page: Page, slot: str) -> bool:
    """Return True if the given slot shows 'Nothing logged'."""
    slots = page.locator("#foodSlots .log-slot")
    count = slots.count()
    for i in range(count):
        s = slots.nth(i)
        header = s.locator(".slot-header h3").text_content().strip().lower()
        if header == slot:
            return s.locator(".empty-slot").count() > 0
    return True


def delete_food_in_slot(page: Page, slot: str, food_name: str):
    """Click the Delete button for a specific food under a specific slot."""
    slots = page.locator("#foodSlots .log-slot")
    count = slots.count()
    for i in range(count):
        s = slots.nth(i)
        header = s.locator(".slot-header h3").text_content().strip().lower()
        if header == slot:
            rows = s.locator(".food-row")
            for j in range(rows.count()):
                row = rows.nth(j)
                name = row.locator(".food-name").text_content().strip()
                if name.lower() == food_name.lower():
                    with page.expect_response(lambda r: "/log/" in r.url):
                        row.locator("button.btn-danger").click()
                    page.wait_for_timeout(200)
                    return
    raise AssertionError(f"Food '{food_name}' not found in slot '{slot}'")


def move_food_in_slot(page: Page, slot: str, food_name: str, target_slot: str):
    """Drag a food row from one slot to another."""
    source_row = None
    slots_el = page.locator("#foodSlots .log-slot")
    count = slots_el.count()
    for i in range(count):
        s = slots_el.nth(i)
        header = s.locator(".slot-header h3").text_content().strip().lower()
        if header == slot:
            rows = s.locator(".food-row")
            for j in range(rows.count()):
                row = rows.nth(j)
                name = row.locator(".food-name").text_content().strip()
                if name.lower() == food_name.lower():
                    source_row = row
                    break
            break

    if source_row is None:
        raise AssertionError(f"Food '{food_name}' not found in slot '{slot}'")

    target_el = None
    for i in range(count):
        s = slots_el.nth(i)
        header = s.locator(".slot-header h3").text_content().strip().lower()
        if header == target_slot:
            target_el = s
            break

    if target_el is None:
        raise AssertionError(f"Target slot '{target_slot}' not found")

    with page.expect_response(lambda r: "/log/" in r.url):
        source_row.drag_to(target_el)
    page.wait_for_timeout(300)


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------

class TestFoodLogRendering:
    """Verify that logged foods appear under the correct slot in the UI."""

    def test_single_food_in_correct_slot(self, food_page):
        ai_send(food_page, "200g chicken breast for lunch")
        names = slot_food_names(food_page, "lunch")
        assert "chicken breast" in names

    def test_multiple_slots_render_independently(self, food_page):
        ai_send(food_page, "2 eggs for breakfast")
        ai_send(food_page, "200g chicken breast for lunch")

        assert "eggs" in slot_food_names(food_page, "breakfast")
        assert "chicken breast" in slot_food_names(food_page, "lunch")
        assert slot_has_empty(food_page, "dinner")
        assert slot_has_empty(food_page, "snack")


class TestDeletePreservesSlots:
    """Regression: deleting a food from one slot must not move foods between slots."""

    def test_delete_breakfast_leaves_lunch_in_lunch(self, food_page):
        ai_send(food_page, "2 eggs for breakfast")
        ai_send(food_page, "200g chicken breast for lunch")

        assert "eggs" in slot_food_names(food_page, "breakfast")
        assert "chicken breast" in slot_food_names(food_page, "lunch")

        delete_food_in_slot(food_page, "breakfast", "eggs")

        assert slot_has_empty(food_page, "breakfast"), \
            f"Breakfast should be empty, but has: {slot_food_names(food_page, 'breakfast')}"
        assert "chicken breast" in slot_food_names(food_page, "lunch"), \
            f"Lunch should still have chicken, but has: {slot_food_names(food_page, 'lunch')}"

    def test_delete_lunch_leaves_breakfast(self, food_page):
        ai_send(food_page, "2 eggs for breakfast")
        ai_send(food_page, "200g chicken breast for lunch")

        delete_food_in_slot(food_page, "lunch", "chicken breast")

        assert "eggs" in slot_food_names(food_page, "breakfast")
        assert slot_has_empty(food_page, "lunch")

    def test_delete_one_of_two_in_same_slot(self, food_page):
        ai_send(food_page, "200g chicken breast for lunch")
        ai_send(food_page, "200g rice for lunch")

        assert "chicken breast" in slot_food_names(food_page, "lunch")
        assert "rice" in slot_food_names(food_page, "lunch")

        delete_food_in_slot(food_page, "lunch", "chicken breast")

        lunch = slot_food_names(food_page, "lunch")
        assert "chicken breast" not in lunch
        assert "rice" in lunch


class TestMovePreservesSlots:
    """Moving a food to another slot must not affect unrelated foods."""

    def test_move_food_appears_in_new_slot(self, food_page):
        ai_send(food_page, "200g chicken breast for lunch")
        ai_send(food_page, "2 eggs for breakfast")

        move_food_in_slot(food_page, "breakfast", "eggs", "dinner")

        assert "eggs" in slot_food_names(food_page, "dinner")
        assert slot_has_empty(food_page, "breakfast")
        assert "chicken breast" in slot_food_names(food_page, "lunch")


class TestFullWorkflow:
    """Multi-step workflow: log across all slots, delete from middle, verify."""

    def test_four_slots_delete_middle(self, food_page):
        ai_send(food_page, "2 eggs for breakfast")
        ai_send(food_page, "200g chicken breast for lunch")
        ai_send(food_page, "200g rice for dinner")
        ai_send(food_page, "1 serving almonds for snack")

        assert not slot_has_empty(food_page, "breakfast")
        assert not slot_has_empty(food_page, "lunch")
        assert not slot_has_empty(food_page, "dinner")
        assert not slot_has_empty(food_page, "snack")

        delete_food_in_slot(food_page, "lunch", "chicken breast")

        assert "eggs" in slot_food_names(food_page, "breakfast")
        assert slot_has_empty(food_page, "lunch")
        assert "rice" in slot_food_names(food_page, "dinner")
        assert "almonds" in slot_food_names(food_page, "snack")

    def test_delete_all_then_relog(self, food_page):
        ai_send(food_page, "2 eggs for breakfast")
        ai_send(food_page, "200g chicken breast for lunch")

        delete_food_in_slot(food_page, "breakfast", "eggs")
        delete_food_in_slot(food_page, "lunch", "chicken breast")

        assert slot_has_empty(food_page, "breakfast")
        assert slot_has_empty(food_page, "lunch")

        ai_send(food_page, "200g rice for dinner")
        assert "rice" in slot_food_names(food_page, "dinner")
        assert slot_has_empty(food_page, "breakfast")
        assert slot_has_empty(food_page, "lunch")
