from flask import Blueprint, abort, flash, g, redirect, render_template, request, url_for
from db import get_db

bp = Blueprint("medicine", __name__, url_prefix="/medicine")

ENTRY_SELECT = (
    "SELECT m.id, m.name AS name, m.generic_name, m.expiration_date, m.quantity"
    "FROM med"
)