from typing import Optional, List
from datetime import datetime, date
from pydantic import BaseModel, Field, ConfigDict, field_validator, model_validator

from pharmatrack.types.animals import AnimalSexEnum, AnimalStatusEnum, SaleFormatEnum, HusbandryStatusEnum
from pharmatrack.types.common import DescriptionStr, ImageURLStr
from pharmatrack.utils.normalize import norm_title


# =========================================================
# 🔹 AnimalGroup (jerárquico, como product_categories)
# =========================================================
class AnimalGroupBase(BaseModel):
    name: str = Field(..., min_length=1, max_length=100)
    parent_id: Optional[int] = Field(None, ge=1, description="Grupo padre (NULL si es raíz)")
    show_public: bool = Field(True, description="Visible en el sitio publico")
    feature_home: bool = Field(False, description="Destacado en la home")
    show_in_nav: bool = Field(True, description="Aparece en el menu del sitio")

    @field_validator("name")
    @classmethod
    def normalize_name(cls, v: str) -> str:
        return norm_title(v)


class AnimalGroupCreate(AnimalGroupBase):
    model_config = ConfigDict(extra="forbid")


class AnimalGroupUpdate(BaseModel):
    name: Optional[str] = Field(None, min_length=1, max_length=100)
    parent_id: Optional[int] = Field(None, ge=1)
    show_public: Optional[bool] = None
    feature_home: Optional[bool] = None
    show_in_nav: Optional[bool] = None

    @field_validator("name", mode="before")
    @classmethod
    def normalize_name(cls, v):
        return norm_title(v) if v is not None else v

    model_config = ConfigDict(extra="forbid")


class AnimalGroupResponse(AnimalGroupBase):
    id: int
    created_at: Optional[datetime] = None
    updated_at: Optional[datetime] = None

    model_config = ConfigDict(from_attributes=True)


class AnimalGroupTreeResponse(AnimalGroupResponse):
    children: List["AnimalGroupTreeResponse"] = Field(default_factory=list)

    model_config = ConfigDict(from_attributes=True)


AnimalGroupTreeResponse.model_rebuild()


# =========================================================
# 🔹 Genus
# =========================================================
class GenusBase(BaseModel):
    name: str = Field(..., min_length=1, max_length=100)
    group_id: Optional[int] = Field(None, ge=1)

    @field_validator("name")
    @classmethod
    def normalize_name(cls, v: str) -> str:
        return norm_title(v)


class GenusCreate(GenusBase):
    model_config = ConfigDict(extra="forbid")


class GenusUpdate(BaseModel):
    name: Optional[str] = Field(None, min_length=1, max_length=100)
    group_id: Optional[int] = Field(None, ge=1)

    @field_validator("name", mode="before")
    @classmethod
    def normalize_name(cls, v):
        return norm_title(v) if v is not None else v

    model_config = ConfigDict(extra="forbid")


class GenusResponse(GenusBase):
    id: int
    group: Optional[AnimalGroupResponse] = None
    created_at: Optional[datetime] = None
    updated_at: Optional[datetime] = None

    model_config = ConfigDict(from_attributes=True)


# =========================================================
# 🔹 Species
# =========================================================
class PriceTier(BaseModel):
    """Escala de precio por cantidad (p. ej. isópodos: 6, 12 o 18 por paquete)."""
    quantity: int = Field(..., ge=1)
    price: float = Field(..., gt=0)

    model_config = ConfigDict(extra="forbid")


class SpeciesBase(BaseModel):
    genus_id: int = Field(..., ge=1)
    name: str = Field(..., min_length=1, max_length=100)
    common_name: Optional[str] = Field(None, min_length=1, max_length=150)
    sale_format: SaleFormatEnum = SaleFormatEnum.INDIVIDUAL
    package_size: Optional[int] = Field(None, ge=2, description="Solo para formato package")
    price_tiers: Optional[List[PriceTier]] = None
    # Ficha de cuidados (sitio público)
    description: Optional[DescriptionStr] = None
    origin: Optional[str] = Field(None, max_length=150)
    temperature: Optional[str] = Field(None, max_length=50)
    humidity: Optional[str] = Field(None, max_length=50)
    adult_size: Optional[str] = Field(None, max_length=50)
    difficulty: Optional[str] = Field(None, max_length=50)
    rarity: Optional[str] = Field(None, max_length=50)
    habitat: Optional[DescriptionStr] = None
    diet: Optional[DescriptionStr] = None
    notes: Optional[DescriptionStr] = None
    image: Optional[str] = Field(None, max_length=250)

    @field_validator("name", "common_name", mode="before")
    @classmethod
    def normalize_names(cls, v):
        return norm_title(v) if v is not None else v

    @field_validator("price_tiers")
    @classmethod
    def sort_tiers(cls, v):
        if not v:
            return None
        return sorted(v, key=lambda t: t.quantity)

    @model_validator(mode="after")
    def check_package_size(self):
        if self.sale_format == SaleFormatEnum.PACKAGE and self.package_size is None:
            raise ValueError("package_size es obligatorio cuando sale_format es package")
        if self.sale_format != SaleFormatEnum.PACKAGE:
            self.package_size = None
        return self


class SpeciesCreate(SpeciesBase):
    model_config = ConfigDict(extra="forbid")


class SpeciesUpdate(BaseModel):
    genus_id: Optional[int] = Field(None, ge=1)
    name: Optional[str] = Field(None, min_length=1, max_length=100)
    common_name: Optional[str] = Field(None, min_length=1, max_length=150)
    sale_format: Optional[SaleFormatEnum] = None
    package_size: Optional[int] = Field(None, ge=2)
    price_tiers: Optional[List[PriceTier]] = None
    description: Optional[DescriptionStr] = None
    origin: Optional[str] = Field(None, max_length=150)
    temperature: Optional[str] = Field(None, max_length=50)
    humidity: Optional[str] = Field(None, max_length=50)
    adult_size: Optional[str] = Field(None, max_length=50)
    difficulty: Optional[str] = Field(None, max_length=50)
    rarity: Optional[str] = Field(None, max_length=50)
    habitat: Optional[DescriptionStr] = None
    diet: Optional[DescriptionStr] = None
    notes: Optional[DescriptionStr] = None
    image: Optional[str] = Field(None, max_length=250)
    show_public: Optional[bool] = None
    # Manejo/cria (privado)
    husbandry_status: Optional[HusbandryStatusEnum] = None
    low_stock_threshold: Optional[int] = Field(None, ge=1)
    private_notes: Optional[str] = Field(None, max_length=5000)

    @field_validator("name", "common_name", mode="before")
    @classmethod
    def normalize_names(cls, v):
        return norm_title(v) if v is not None else v

    model_config = ConfigDict(extra="forbid")


class SpeciesResponse(SpeciesBase):
    id: int
    genus: Optional[GenusResponse] = None
    created_at: Optional[datetime] = None
    updated_at: Optional[datetime] = None

    model_config = ConfigDict(from_attributes=True)


class SpeciesAdminResponse(SpeciesResponse):
    """Igual que SpeciesResponse pero con los campos privados de manejo/cria.
    Solo la usan las rutas admin de /species; el catalogo publico usa
    SpeciesResponse (sin estos campos) para no filtrar datos internos."""
    husbandry_status: HusbandryStatusEnum = HusbandryStatusEnum.ACTIVE
    low_stock_threshold: Optional[int] = None
    private_notes: Optional[str] = None
    show_public: bool = True

    model_config = ConfigDict(from_attributes=True)


# =========================================================
# 🔹 Morph
# =========================================================
class MorphBase(BaseModel):
    species_id: int = Field(..., ge=1)
    name: str = Field(..., min_length=1, max_length=100)
    description: Optional[DescriptionStr] = None
    image: Optional[str] = Field(None, max_length=250)

    @field_validator("name")
    @classmethod
    def normalize_name(cls, v: str) -> str:
        return norm_title(v)


class MorphCreate(MorphBase):
    model_config = ConfigDict(extra="forbid")


class MorphUpdate(BaseModel):
    species_id: Optional[int] = Field(None, ge=1)
    name: Optional[str] = Field(None, min_length=1, max_length=100)
    description: Optional[DescriptionStr] = None
    image: Optional[str] = Field(None, max_length=250)
    show_public: Optional[bool] = None
    # Manejo/cria (privado) — el morph es independiente del nominal
    husbandry_status: Optional[HusbandryStatusEnum] = None
    low_stock_threshold: Optional[int] = Field(None, ge=1)
    private_notes: Optional[str] = Field(None, max_length=5000)

    @field_validator("name", mode="before")
    @classmethod
    def normalize_name(cls, v):
        return norm_title(v) if v is not None else v

    model_config = ConfigDict(extra="forbid")


class MorphResponse(MorphBase):
    id: int
    created_at: Optional[datetime] = None
    updated_at: Optional[datetime] = None

    model_config = ConfigDict(from_attributes=True)


class MorphAdminResponse(MorphResponse):
    """Igual que MorphResponse pero con los campos privados de manejo/cria.
    Solo la usan las rutas admin de /morphs; el catalogo publico (embebido en
    los animales) usa MorphResponse para no filtrar datos internos."""
    husbandry_status: HusbandryStatusEnum = HusbandryStatusEnum.ACTIVE
    low_stock_threshold: Optional[int] = None
    private_notes: Optional[str] = None
    show_public: bool = True

    model_config = ConfigDict(from_attributes=True)


# =========================================================
# 🔹 Animal
# =========================================================
class AnimalBase(BaseModel):
    species_id: int = Field(..., ge=1)
    sex: AnimalSexEnum = AnimalSexEnum.UNKNOWN
    birth_date: Optional[date] = None
    price: float = Field(..., ge=0)
    price_cost: float = Field(0, ge=0)
    description: Optional[DescriptionStr] = None
    image: Optional[ImageURLStr] = None

    # Documentación legal (SEMARNAT/UMA) — opcional
    # Precio anterior (tachado) para ofertas en la tienda
    compare_at_price: Optional[float] = Field(None, gt=0)
    requires_legal_doc: bool = False
    legal_doc: Optional[str] = Field(None, max_length=150, description="Folio/referencia del documento de procedencia legal")
    legal_doc_url: Optional[str] = Field(None, max_length=500, description="URL del documento escaneado")


class AnimalCreate(AnimalBase):
    code: Optional[str] = Field(
        None, min_length=1, max_length=50,
        description="Identificador único del animal; se genera automáticamente si se omite",
    )
    morph_ids: List[int] = Field(default_factory=list)
    photos: List[str] = Field(default_factory=list, description="URLs de fotos (la primera es la principal si no se envía image)")
    stock: int = Field(
        1, ge=1,
        description="Unidades idénticas en venta (cepas/paquetes); individual siempre 1",
    )

    model_config = ConfigDict(
        extra="forbid",
        json_schema_extra={
            "example": {
                "species_id": 1,
                "sex": "female",
                "birth_date": "2025-09-15",
                "price": 3500.0,
                "price_cost": 1200.0,
                "code": "BP-2025-001",
                "morph_ids": [1, 2],
                "description": "Ball python hembra Banana Pastel",
            }
        },
    )


class AnimalUpdate(BaseModel):
    species_id: Optional[int] = Field(None, ge=1)
    sex: Optional[AnimalSexEnum] = None
    birth_date: Optional[date] = None
    price: Optional[float] = Field(None, ge=0)
    price_cost: Optional[float] = Field(None, ge=0)
    description: Optional[DescriptionStr] = None
    image: Optional[ImageURLStr] = None
    code: Optional[str] = Field(None, min_length=1, max_length=50)
    morph_ids: Optional[List[int]] = None
    photos: Optional[List[str]] = Field(None, description="Reemplaza TODAS las fotos del animal")
    status: Optional[AnimalStatusEnum] = None
    requires_legal_doc: Optional[bool] = None
    legal_doc: Optional[str] = Field(None, max_length=150)
    legal_doc_url: Optional[str] = Field(None, max_length=500)
    stock: Optional[int] = Field(None, ge=1, description="Ajusta las unidades disponibles (resurtir cepa)")
    compare_at_price: Optional[float] = Field(None, gt=0, description="Precio anterior (tachado); null quita la oferta")

    @field_validator("status")
    @classmethod
    def forbid_manual_sold(cls, v):
        # "sold" lo asigna el flujo de venta, nunca el cliente
        if v == AnimalStatusEnum.SOLD:
            raise ValueError("status 'sold' is managed by the sale flow and cannot be set manually")
        return v

    model_config = ConfigDict(extra="forbid")


class PublicAnimalResponse(BaseModel):
    """Vista pública del catálogo: sin costos, producto gemelo ni documentación legal."""
    id: int
    code: str
    status: AnimalStatusEnum
    sex: AnimalSexEnum
    birth_date: Optional[date] = None
    price: float
    compare_at_price: Optional[float] = None
    description: Optional[str] = None
    image: Optional[str] = None
    species: Optional[SpeciesResponse] = None
    morphs: List[MorphResponse] = Field(default_factory=list)
    photos: List[str] = Field(default_factory=list)

    @field_validator("photos", mode="before")
    @classmethod
    def photos_to_urls(cls, v):
        return [p.url if hasattr(p, "url") else p for p in v]

    model_config = ConfigDict(from_attributes=True)


class AnimalResponse(AnimalBase):
    id: int
    code: str
    status: AnimalStatusEnum
    product_id: int
    # Unidades disponibles (lotes del producto gemelo); individuales: 1
    stock: Optional[int] = None
    species: Optional[SpeciesResponse] = None
    morphs: List[MorphResponse] = Field(default_factory=list)
    photos: List[str] = Field(default_factory=list)
    created_at: Optional[datetime] = None
    updated_at: Optional[datetime] = None

    @field_validator("photos", mode="before")
    @classmethod
    def photos_to_urls(cls, v):
        # La relación ORM entrega objetos AnimalPhoto; el API expone solo URLs
        return [p.url if hasattr(p, "url") else p for p in v]

    model_config = ConfigDict(from_attributes=True)
