from datetime import datetime
from database.sheets import append_order
from src.logger import get_logger

log = get_logger("tool.order")

DOUGH_OPTIONS = ["Classic", "Thin & Crispy", "Thick & Fluffy", "Stuffed Crust", "Gluten-Free"]
SAUCE_OPTIONS = ["Tomato Marinara", "BBQ", "Alfredo", "Pesto", "Spicy Arrabbiata"]
TOPPING_OPTIONS = [
    "Pepperoni", "Salami", "Ham", "Chicken", "Beef",
    "Mozzarella", "Cheddar", "Parmesan",
    "Mushrooms", "Olives", "Onions", "Bell Peppers", "Jalapeños",
    "Spinach", "Tomatoes", "Corn", "Pineapple",
]
COOK_STYLE_OPTIONS = ["Regular", "Well Done", "Light Bake"]

TOOL_DEFINITION = {
    "type": "function",
    "function": {
        "name": "place_order",
        "description": (
            "Place a pizza order once the customer has confirmed all their choices. "
            "Only call this after you have collected: customer name, phone number, "
            "delivery location, dough type, sauce, toppings, and cook style."
        ),
        "parameters": {
            "type": "object",
            "properties": {
                "customer_name": {
                    "type": "string",
                    "description": "Full name of the customer"
                },
                "phone": {
                    "type": "string",
                    "description": "Customer's phone number"
                },
                "location": {
                    "type": "string",
                    "description": "Delivery address or location description"
                },
                "dough": {
                    "type": "string",
                    "enum": DOUGH_OPTIONS,
                    "description": "Pizza base/dough type"
                },
                "sauce": {
                    "type": "string",
                    "enum": SAUCE_OPTIONS,
                    "description": "Pizza sauce"
                },
                "toppings": {
                    "type": "array",
                    "items": {"type": "string"},
                    "description": "List of toppings chosen by the customer"
                },
                "cook_style": {
                    "type": "string",
                    "enum": COOK_STYLE_OPTIONS,
                    "description": "How the pizza should be cooked"
                },
                "notes": {
                    "type": "string",
                    "description": "Any special instructions or extra details (optional)"
                },
            },
            "required": ["customer_name", "phone", "location", "dough", "sauce", "toppings", "cook_style"],
        },
    },
}


async def execute(
    customer_name: str,
    phone: str,
    location: str,
    dough: str,
    sauce: str,
    toppings: list[str],
    cook_style: str,
    notes: str = "",
) -> str:
    log.info(
        "Placing order for %s | %s | dough=%s sauce=%s toppings=%s cook=%s",
        customer_name, phone, dough, sauce, toppings, cook_style,
    )
    order = {
        "timestamp": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
        "customer_name": customer_name,
        "phone": phone,
        "location": location,
        "dough": dough,
        "sauce": sauce,
        "toppings": ", ".join(toppings),
        "cook_style": cook_style,
        "notes": notes,
    }
    try:
        order_id = await append_order(order)
        return (
            f"Order #{order_id} confirmed!\n"
            f"**{customer_name}** — {phone}\n"
            f"Delivering to: {location}\n"
            f"Pizza: {dough} base, {sauce} sauce, {cook_style}\n"
            f"Toppings: {', '.join(toppings)}\n"
            f"{f'Notes: {notes}' if notes else ''}\n"
            f"Your order is with the kitchen. Estimated time: 30-45 mins."
        )
    except Exception as exc:
        log.exception("Failed to save order to sheet")
        return f"Order details collected but failed to save: {exc}"
