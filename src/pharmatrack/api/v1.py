from fastapi import APIRouter
from .routes import (
    permissions, roles, users, branches, auth,
    product_categories, products, sales, sale_payments,
    sale_details, refund_products, suppliers, purchases,
    purchase_details, product_batch, sale_batch_usage,
    product_master, product_brand, ingredients, stats, sensor_readings, dashboard, calendar,
    animal_taxonomy, animals, public_animals, public_species, public_products, image_cache, articles,
    settings, shop,
)

api_v1_router = APIRouter(prefix="/api/v1")

api_v1_router.include_router(auth.router)
api_v1_router.include_router(settings.router)
api_v1_router.include_router(permissions.router)
api_v1_router.include_router(roles.router)
api_v1_router.include_router(users.router)
api_v1_router.include_router(branches.router)
api_v1_router.include_router(ingredients.router)
api_v1_router.include_router(product_brand.router)
api_v1_router.include_router(products.router)
api_v1_router.include_router(product_batch.router)
api_v1_router.include_router(product_master.router)
api_v1_router.include_router(product_categories.router)
api_v1_router.include_router(sales.router)
api_v1_router.include_router(sale_payments.router)
api_v1_router.include_router(sale_details.router)
api_v1_router.include_router(sale_batch_usage.router)   # ← montado
api_v1_router.include_router(refund_products.router)
api_v1_router.include_router(suppliers.router)
api_v1_router.include_router(purchases.router)
api_v1_router.include_router(purchase_details.router)
api_v1_router.include_router(stats.router)
api_v1_router.include_router(sensor_readings.router)
api_v1_router.include_router(dashboard.router)
api_v1_router.include_router(calendar.router)
api_v1_router.include_router(animal_taxonomy.groups_router)
api_v1_router.include_router(animal_taxonomy.genera_router)
api_v1_router.include_router(animal_taxonomy.species_router)
api_v1_router.include_router(animal_taxonomy.morphs_router)
api_v1_router.include_router(animals.router)
api_v1_router.include_router(public_animals.router)
api_v1_router.include_router(public_species.router)
api_v1_router.include_router(image_cache.router)
api_v1_router.include_router(articles.router)
api_v1_router.include_router(articles.public_router)
api_v1_router.include_router(public_products.router)
api_v1_router.include_router(shop.router)
api_v1_router.include_router(shop.orders_router)