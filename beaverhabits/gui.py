import os
import random
from typing import Optional
from fastapi import Depends, FastAPI, Request
from fastapi.responses import RedirectResponse

from nicegui import Client, app, ui

from beaverhabits.app.crud import get_user_habit_list

from .app.db import HabitModel, User
from .app.auth import (
    user_authenticate,
    user_check_token,
    user_create,
    user_create_token,
)
from .app.users import current_active_user

from .configs import settings
from .view import HabitList
from .utils import dummy_records
from .frontend.index_page import habit_list_ui, index_page_ui

INDEX_PATH = MOUNT_PATH = "/gui"
LOGIN_PATH, REGISTER_PATH = "/gui/login", "/gui/register"
UNRESTRICTED_PAGE_ROUTES = (LOGIN_PATH, REGISTER_PATH)


@ui.page("/")
async def index_page(
    user: User = Depends(current_active_user),
) -> None:
    ui.label(f"Hello, {user.email}")

    habit_items = await get_user_habit_list(user)
    habits = HabitList(items=habit_items, on_change=habit_list_ui.refresh)
    index_page_ui(habits)


@ui.page("/demo")
async def demo():
    items = []
    for name in ["Order pizz", "Running", "Table Tennis", "Clean", "Call mom"]:
        pick = lambda: random.randint(0, 3) == 0
        days = settings.INDEX_HABIT_ITEM_COUNT
        habit = HabitModel(name=name, records=dummy_records(days, pick=pick))
        items.append(habit)
    habits = HabitList(items=items, on_change=habit_list_ui.refresh)

    index_page_ui(habits)

    # NOTE dark mode will be persistent for each user across tabs and server restarts
    # ui.dark_mode().bind_value(app.storage.user, "dark_mode")
    # ui.checkbox("dark mode").bind_value(app.storage.user, "dark_mode")


@ui.page("/login")
async def login_page() -> Optional[RedirectResponse]:
    async def try_login():
        user = await user_authenticate(email=email.value, password=password.value)
        token = user and await user_create_token(user)
        if token is not None:
            app.storage.user.update({"auth_token": token})
            ui.navigate.to(app.storage.user.get("referrer_path", "/"))
        else:
            ui.notify("email or password wrong!", color="negative")

    if await user_check_token(app.storage.user.get("auth_token", None)):
        return RedirectResponse(INDEX_PATH)

    with ui.card().classes("absolute-center shadow-none w-96"):
        email = ui.input("email").on("keydown.enter", try_login)
        password = ui.input("password", password=True, password_toggle_button=True).on(
            "keydown.enter", try_login
        )
        ui.button("Continue", on_click=try_login).props('padding="xs lg"')
        ui.separator()
        with ui.row():
            ui.label("New around here?").classes("text-sm")
            ui.link("Create account", target="/register").classes("text-sm")


@ui.page("/register")
async def register():
    async def try_register():
        try:
            user = await user_create(email=email.value, password=password.value)
        except Exception as e:
            ui.notify(str(e))
        else:
            token = user and await user_create_token(user)
            if token is not None:
                app.storage.user.update({"auth_token": token})
                ui.navigate.to(app.storage.user.get("referrer_path", "/"))

    with ui.card().classes("absolute-center shadow-none w-96"):
        email = ui.input("email").on("keydown.enter", try_register)
        password = ui.input("password", password=True, password_toggle_button=True).on(
            "keydown.enter", try_register
        )

        with ui.element("div").classes("flex mt-4 justify-between items-center"):
            ui.button("Register", on_click=try_register)
        ui.separator()
        with ui.row():
            ui.label("Already have an account?")
            ui.link("Log in", target="/login")


def init_gui_routes(fastapi_app: FastAPI):
    @app.middleware("http")
    async def AuthMiddleware(request: Request, call_next):
        client_page_routes = (
            os.path.join(MOUNT_PATH + x) for x in Client.page_routes.values()
        )
        if not await user_check_token(app.storage.user.get("auth_token", None)):
            if (
                request.url.path in client_page_routes
                and request.url.path not in UNRESTRICTED_PAGE_ROUTES
            ):
                root_path = request.scope["root_path"]
                app.storage.user["referrer_path"] = request.url.path.removeprefix(
                    root_path
                )
                return RedirectResponse(request.url_for(login_page.__name__))

        # Remove original authorization header
        request.scope["headers"] = [
            e for e in request.scope["headers"] if not e[0] == b"authorization"
        ]
        # # add new authorization header
        request.scope["headers"].append(
            (b"authorization", f"Bearer {app.storage.user.get('auth_token')}".encode())
        )

        return await call_next(request)

    ui.run_with(
        fastapi_app,
        mount_path=MOUNT_PATH,  # NOTE this can be omitted if you want the paths passed to @ui.page to be at the root
        storage_secret=settings.STORAGE_SECRET,
        dark=True,
    )
