"""Seed the development database with a small, varied store catalog."""

from .database import SessionLocal, engine
from .models import Base, Category, Product


CATALOG = {
    "Computers": [
        ("Mechanical Keyboard", "RGB mechanical keyboard with blue switches", 89.99, 12),
        ("Gaming Mouse", "Ergonomic 16000 DPI wireless gaming mouse", 49.99, 25),
        ("Gaming Monitor 27-inch", "144Hz QHD IPS monitor", 279.99, 4),
        ("USB Webcam", "1080p webcam with privacy cover", 39.99, 18),
        ("Laptop Pro 14", "14-inch laptop with 16GB memory", 899.99, 6),
        ("Wireless Keyboard", "Slim Bluetooth keyboard", 34.99, 20),
    ],
    "Audio": [
        ("Noise Cancelling Headphones", "Over-ear wireless headphones with ANC", 149.99, 8),
        ("Waterproof Bluetooth Speaker", "Portable 20W outdoor speaker", 59.99, 0),
        ("Wireless Earbuds", "Compact earbuds with charging case", 69.99, 30),
        ("USB Microphone", "Cardioid microphone for streaming", 79.99, 10),
        ("Soundbar Mini", "Compact television soundbar", 99.99, 7),
    ],
    "Accessories": [
        ("USB-C Fast Charging Cable", "Braided 2-meter 100W charging cable", 14.99, 50),
        ("Aluminum Laptop Stand", "Foldable ergonomic laptop riser", 34.99, 15),
        ("Wireless Charger", "15W Qi charging pad", 24.99, 22),
        ("Travel Adapter", "Universal adapter with USB ports", 29.99, 17),
        ("Screen Protector", "Tempered glass phone protector", 9.99, 40),
    ],
    "Smart Home": [
        ("Smart Bulb", "Color changing Wi-Fi LED bulb", 19.99, 32),
        ("Smart Plug", "Wi-Fi outlet with energy monitoring", 17.99, 28),
        ("Video Doorbell", "HD doorbell with motion alerts", 119.99, 5),
        ("Robot Vacuum", "Scheduled vacuum with app control", 249.99, 3),
        ("Air Quality Sensor", "Indoor air monitor", 44.99, 11),
    ],
    "Office": [
        ("Ergonomic Office Chair", "Adjustable lumbar support chair", 199.99, 9),
        ("Desk Lamp", "Dimmable LED desk lamp", 29.99, 19),
        ("Notebook Set", "Three premium ruled notebooks", 12.99, 60),
        ("Wireless Presenter", "USB presentation clicker", 22.99, 14),
        ("Cable Organizer", "Desktop cable management kit", 11.99, 35),
    ],
    "Gaming": [
        ("Gaming Controller", "Wireless controller for PC and console", 59.99, 16),
        ("Gaming Headset", "Surround sound headset with microphone", 74.99, 13),
        ("Mouse Pad XL", "Extended non-slip gaming mouse pad", 19.99, 24),
        ("Console Dock", "Charging dock for two controllers", 27.99, 12),
        ("Gaming Chair", "Reclining chair with headrest", 229.99, 2),
    ],
}


def seed() -> None:
    """Create tables and insert the catalog once."""
    Base.metadata.create_all(bind=engine)
    with SessionLocal() as db:
        if db.query(Category).count():
            return
        for category_name, products in CATALOG.items():
            category = Category(name=category_name, description=f"{category_name} products")
            db.add(category)
            db.flush()
            db.add_all(
                Product(
                    name=name,
                    description=description,
                    price=price,
                    stock=stock,
                    category_id=category.id,
                )
                for name, description, price, stock in products
            )
        db.commit()


if __name__ == "__main__":
    seed()
