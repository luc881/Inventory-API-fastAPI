import json

from fastapi import APIRouter, HTTPException
from typing import Literal, Optional

from pydantic import BaseModel, EmailStr
from starlette import status

from ...db.session import db_dependency
from ...models.app_settings.orm import AppSetting
from ...config import settings
from ...utils.email import send_test_email, send_sample_order_emails
from ...utils.permissions import CAN_READ_SALES, CAN_UPDATE_SALES, CAN_UPDATE_SETTINGS

router = APIRouter(prefix="/settings", tags=["settings"])

# Defaults de la plantilla del correo de ticket; lo guardado los sobreescribe
EMAIL_TICKET_DEFAULTS = {
    "business_name": "Opuntia Den",
    "intro_message": "",
    "footer_message": "Gracias por su compra.",
    # Logo y color de marca de TODOS los correos. El logo debe ser una URL
    # publica: los clientes de correo no pueden leer archivos del servidor.
    "logo_url": "https://www.opuntiaden.com/logo/opuntia-logo.png",  # 640px, ~110 KB
    "accent_color": "#8C9E6E",
    # Textos de los correos de pedido (el resumen y los datos van aparte)
    "order_intro_pickup": (
        "Recibimos tu pedido de entrega personal en CDMX. En cuanto se acredite "
        "tu pago te escribimos por WhatsApp para acordar la entrega."
    ),
    "order_intro_shipping": (
        "Recibimos tu pedido. Te confirmamos disponibilidad, envio y total en "
        "breve; todavia no se cobra nada."
    ),
    "paid_intro": (
        "Listo! Recibimos tu pago. Te escribimos por WhatsApp para acordar el "
        "punto y la hora de entrega."
    ),
}


def get_email_ticket_template(db) -> dict:
    row = db.query(AppSetting).filter(AppSetting.key == "email_ticket").first()
    stored = json.loads(row.value) if row else {}
    return {**EMAIL_TICKET_DEFAULTS, **stored}


class EmailTicketTemplate(BaseModel):
    business_name: str = EMAIL_TICKET_DEFAULTS["business_name"]
    intro_message: str = ""
    footer_message: str = EMAIL_TICKET_DEFAULTS["footer_message"]
    logo_url: str = EMAIL_TICKET_DEFAULTS["logo_url"]
    accent_color: str = EMAIL_TICKET_DEFAULTS["accent_color"]
    order_intro_pickup: str = EMAIL_TICKET_DEFAULTS["order_intro_pickup"]
    order_intro_shipping: str = EMAIL_TICKET_DEFAULTS["order_intro_shipping"]
    paid_intro: str = EMAIL_TICKET_DEFAULTS["paid_intro"]


@router.get("/email-ticket", dependencies=CAN_READ_SALES,
            summary="Plantilla del correo de ticket")
def read_email_ticket(db: db_dependency):
    return get_email_ticket_template(db)


@router.put("/email-ticket", dependencies=CAN_UPDATE_SALES,
            summary="Guardar plantilla del correo de ticket")
def update_email_ticket(body: EmailTicketTemplate, db: db_dependency):
    if not body.business_name.strip():
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
                            detail="El nombre del negocio no puede quedar vacio.")
    row = db.query(AppSetting).filter(AppSetting.key == "email_ticket").first()
    if not row:
        row = AppSetting(key="email_ticket", value="{}")
        db.add(row)
    row.value = json.dumps(body.model_dump())
    db.commit()
    return get_email_ticket_template(db)


class TestEmailRequest(BaseModel):
    to: Optional[EmailStr] = None
    # "simple" = prueba minima; "order"/"paid" = los correos reales del pedido
    kind: Literal["simple", "order", "paid"] = "simple"


@router.post("/test-email", dependencies=CAN_UPDATE_SALES,
             summary="Mandar un correo de prueba y ver el error si falla")
def test_email(body: TestEmailRequest, db: db_dependency):
    """Devuelve el error real de Resend en lugar de tragarselo en un log.

    Sin `to` usa ORDER_NOTIFY_EMAIL: es el buzon del negocio y el que de
    verdad interesa probar."""
    to = body.to or settings.order_notify_email.strip()
    if not to:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail="No hay a donde mandar: falta ORDER_NOTIFY_EMAIL en el servidor.",
        )
    if body.kind == "simple":
        return send_test_email(to)
    return send_sample_order_emails(to, body.kind, get_email_ticket_template(db))


# =========================================================
# Ajustes del sitio publico
# =========================================================
# Media del sitio publico. Cloudinary es la unica fuente: estos defaults son
# las versiones sembradas, no archivos del repo (ver docs/superpowers/specs/
# 2026-08-18-site-media-design.md). Agregar un slot aqui es un cambio de
# diseno del sitio, por eso no hay slots dinamicos.
SITE_MEDIA_DEFAULTS = {
    "hero_video_mp4": "https://res.cloudinary.com/dnxavfqhj/video/upload/v1787115691/pukyu6z7wfkpqaifzmor.mp4",
    "hero_video_webm": "https://res.cloudinary.com/dnxavfqhj/video/upload/v1787115692/jjzcsbb3u6nccqmydh9z.webm",
    "hero_poster": "https://res.cloudinary.com/dnxavfqhj/image/upload/v1787115694/bbrlmcwkgjngvme9thzu.jpg",
    "moss_tall": "https://res.cloudinary.com/dnxavfqhj/image/upload/v1787115695/bfqjr7t2tu5vrl0mdkhr.jpg",
    "moss_wide": "https://res.cloudinary.com/dnxavfqhj/image/upload/v1787115697/no2ujblgtav0rjemgpix.jpg",
    "leaf_litter": "https://res.cloudinary.com/dnxavfqhj/image/upload/v1787115698/rmkknlujheewmo2isf8l.jpg",
    "terrarium": "https://res.cloudinary.com/dnxavfqhj/image/upload/v1787115699/acknugtzwqg7iecawvbu.jpg",
    "isopod_zebra": "https://res.cloudinary.com/dnxavfqhj/image/upload/v1787115701/gjcseewc5tclvmflhkpt.png",
    "isopod_cubaris": "https://res.cloudinary.com/dnxavfqhj/image/upload/v1787115702/ko1qxvsltrlgb2d6ltjd.png",
}

SITE_DEFAULTS = {
    "show_category_browse": True,  # seccion "Explora por grupo" en la home
    # Apagado: el sitio solo ofrece entrega personal en CDMX y la API rechaza
    # pedidos con envio (ver create_order en routes/shop.py)
    "shipping_enabled": True,
    "media": SITE_MEDIA_DEFAULTS,
}


def get_site_settings(db) -> dict:
    row = db.query(AppSetting).filter(AppSetting.key == "site").first()
    stored = json.loads(row.value) if row else {}
    # media se mezcla aparte: un slot guardado no debe esconder los defaults
    # de los otros ocho.
    media = {**SITE_MEDIA_DEFAULTS, **stored.get("media", {})}
    return {**SITE_DEFAULTS, **stored, "media": media}


class SiteMedia(BaseModel):
    hero_video_mp4: Optional[str] = None
    hero_video_webm: Optional[str] = None
    hero_poster: Optional[str] = None
    moss_tall: Optional[str] = None
    moss_wide: Optional[str] = None
    leaf_litter: Optional[str] = None
    terrarium: Optional[str] = None
    isopod_zebra: Optional[str] = None
    isopod_cubaris: Optional[str] = None


class SiteSettings(BaseModel):
    # Todos opcionales: el PUT es parcial y solo escribe lo que llega.
    # Sin esto, Pydantic rellenaba los ausentes con su default y los persistia,
    # asi que tocar un ajuste reseteaba los demas.
    show_category_browse: Optional[bool] = None
    shipping_enabled: Optional[bool] = None
    media: Optional[SiteMedia] = None


# Lectura publica (sin auth): el sitio la consulta para armar la home
@router.get("/site", summary="Ajustes publicos del sitio")
def read_site_settings(db: db_dependency):
    return get_site_settings(db)


@router.put("/site", dependencies=CAN_UPDATE_SETTINGS,
            summary="Guardar ajustes del sitio")
def update_site_settings(body: SiteSettings, db: db_dependency):
    row = db.query(AppSetting).filter(AppSetting.key == "site").first()
    if not row:
        row = AppSetting(key="site", value="{}")
        db.add(row)

    stored = json.loads(row.value)
    # exclude_unset=True filtra campos ausentes, pero no un null explícito.
    # Si el cliente manda {"shipping_enabled": null}, Pydantic lo persiste.
    # Filtramos también los None: "null" significa "no cambiar", no "escribir null".
    patch = {k: v for k, v in body.model_dump(exclude_unset=True).items() if v is not None}

    # media se mezcla un nivel mas adentro: mandar un slot no borra los otros
    if "media" in patch:
        patch["media"] = {
            **stored.get("media", {}),
            **{k: v for k, v in patch["media"].items() if v is not None},
        }

    row.value = json.dumps({**stored, **patch})
    db.commit()
    return get_site_settings(db)
