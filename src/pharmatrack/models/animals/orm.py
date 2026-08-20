from sqlalchemy import (
    JSON, String, BigInteger, Numeric, Text, TIMESTAMP, Date, ForeignKey,
    Table, Column, UniqueConstraint, Boolean,
)
from sqlalchemy.sql import func
from sqlalchemy.orm import Mapped, mapped_column, relationship
from datetime import datetime, date
from decimal import Decimal
from typing import Optional

from ...db.session import Base


class AnimalGroup(Base):
    """Agrupación jerárquica libre (Arácnidos → Tarántulas, etc.)."""
    __tablename__ = "animal_groups"

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    name: Mapped[str] = mapped_column(String(100), nullable=False)
    parent_id: Mapped[Optional[int]] = mapped_column(
        BigInteger, ForeignKey("animal_groups.id", ondelete="RESTRICT"), nullable=True
    )
    # Visible en el sitio publico (nav, explorar por grupo, resultados).
    # Se controla por grupo raiz; ocultar un raiz oculta sus descendientes.
    show_public: Mapped[bool] = mapped_column(Boolean, nullable=False, server_default="1")
    # Destacado en la home como mini-catalogo de sus especies (solo grupo raiz)
    feature_home: Mapped[bool] = mapped_column(Boolean, nullable=False, server_default="0")
    # Aparece en el menu del sitio. Separado de show_public: un grupo puede
    # estar activo (sus animales se venden, se puede destacar en la home) sin
    # ocupar un lugar en la navegacion.
    show_in_nav: Mapped[bool] = mapped_column(Boolean, nullable=False, server_default="1")

    created_at: Mapped[datetime] = mapped_column(TIMESTAMP(timezone=False), server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(
        TIMESTAMP(timezone=False), server_default=func.now(), onupdate=func.now()
    )

    parent = relationship("AnimalGroup", remote_side=[id], back_populates="children")
    children = relationship("AnimalGroup", back_populates="parent")
    genera = relationship("Genus", back_populates="group")


class Genus(Base):
    __tablename__ = "genera"

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    name: Mapped[str] = mapped_column(String(100), nullable=False, unique=True)
    group_id: Mapped[Optional[int]] = mapped_column(
        BigInteger, ForeignKey("animal_groups.id", ondelete="RESTRICT"), nullable=True, index=True
    )

    created_at: Mapped[datetime] = mapped_column(TIMESTAMP(timezone=False), server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(
        TIMESTAMP(timezone=False), server_default=func.now(), onupdate=func.now()
    )

    group = relationship("AnimalGroup", back_populates="genera")
    species = relationship("Species", back_populates="genus")


class Species(Base):
    __tablename__ = "species"
    __table_args__ = (UniqueConstraint("genus_id", "name", name="uq_species_genus_name"),)

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    genus_id: Mapped[int] = mapped_column(
        BigInteger, ForeignKey("genera.id", ondelete="RESTRICT"), nullable=False, index=True
    )
    name: Mapped[str] = mapped_column(String(100), nullable=False)
    common_name: Mapped[Optional[str]] = mapped_column(String(150), nullable=True)
    # Cómo se vende la especie: individual (folio único), package (de N) o colony (cepa)
    sale_format: Mapped[str] = mapped_column(String(20), nullable=False, server_default="individual")
    package_size: Mapped[Optional[int]] = mapped_column(BigInteger, nullable=True)
    # Escalas de precio por cantidad: [{"quantity": 6, "price": 150}, ...]
    price_tiers: Mapped[Optional[list]] = mapped_column(JSON, nullable=True)
    # Ficha de cuidados para el sitio público (texto libre, todo opcional)
    description: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    origin: Mapped[Optional[str]] = mapped_column(String(150), nullable=True)
    temperature: Mapped[Optional[str]] = mapped_column(String(50), nullable=True)
    humidity: Mapped[Optional[str]] = mapped_column(String(50), nullable=True)
    adult_size: Mapped[Optional[str]] = mapped_column(String(50), nullable=True)
    difficulty: Mapped[Optional[str]] = mapped_column(String(50), nullable=True)
    rarity: Mapped[Optional[str]] = mapped_column(String(50), nullable=True)
    # Ficha descriptiva extendida (secciones largas del detalle público)
    habitat: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    diet: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    notes: Mapped[Optional[str]] = mapped_column(Text, nullable=True)

    # Visible en el sitio publico. Independiente del inventario: una especie
    # puede estar en cultivo y no anunciarse todavia. El grupo raiz manda por
    # encima (si el grupo esta oculto, esto no la rescata).
    show_public: Mapped[bool] = mapped_column(Boolean, nullable=False, server_default="1")

    # Foto del taxon para la tarjeta del catalogo. Las fotos "reales" cuelgan
    # del ejemplar; esta es la que se usa cuando la especie no tiene ninguno.
    image: Mapped[Optional[str]] = mapped_column(String(250), nullable=True)

    # === Manejo/cria (PRIVADO — nunca se expone en la API publica) ===
    # Estado de cria; low_stock_threshold NULL = usa el default global del panel
    husbandry_status: Mapped[str] = mapped_column(String(20), nullable=False, server_default="active")
    low_stock_threshold: Mapped[Optional[int]] = mapped_column(BigInteger, nullable=True)
    private_notes: Mapped[Optional[str]] = mapped_column(Text, nullable=True)

    created_at: Mapped[datetime] = mapped_column(TIMESTAMP(timezone=False), server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(
        TIMESTAMP(timezone=False), server_default=func.now(), onupdate=func.now()
    )

    genus = relationship("Genus", back_populates="species")
    morphs = relationship("Morph", back_populates="species")
    animals = relationship("Animal", back_populates="species")


class Morph(Base):
    __tablename__ = "morphs"
    __table_args__ = (UniqueConstraint("species_id", "name", name="uq_morph_species_name"),)

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    species_id: Mapped[int] = mapped_column(
        BigInteger, ForeignKey("species.id", ondelete="RESTRICT"), nullable=False, index=True
    )
    name: Mapped[str] = mapped_column(String(100), nullable=False)
    description: Mapped[Optional[str]] = mapped_column(Text, nullable=True)

    # Visible en el sitio publico, independiente de su especie: se puede
    # esconder un morph suelto dejando el resto a la venta.
    show_public: Mapped[bool] = mapped_column(Boolean, nullable=False, server_default="1")

    # Foto propia del morph: sin ella, todos los morphs de una especie
    # compartirian imagen y se perderia justo lo que los distingue.
    image: Mapped[Optional[str]] = mapped_column(String(250), nullable=True)

    # === Manejo/cria (PRIVADO — nunca se expone en la API publica) ===
    # El morph maneja su cria independiente del nominal (puede estar en cultivo
    # aunque la especie no lo esté, o al revés). Mismo esquema que Species.
    husbandry_status: Mapped[str] = mapped_column(String(20), nullable=False, server_default="active")
    low_stock_threshold: Mapped[Optional[int]] = mapped_column(BigInteger, nullable=True)
    private_notes: Mapped[Optional[str]] = mapped_column(Text, nullable=True)

    created_at: Mapped[datetime] = mapped_column(TIMESTAMP(timezone=False), server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(
        TIMESTAMP(timezone=False), server_default=func.now(), onupdate=func.now()
    )

    species = relationship("Species", back_populates="morphs")


animal_has_morphs = Table(
    "animal_has_morphs",
    Base.metadata,
    Column("animal_id", BigInteger, ForeignKey("animals.id", ondelete="CASCADE"), primary_key=True),
    Column("morph_id", BigInteger, ForeignKey("morphs.id", ondelete="CASCADE"), primary_key=True),
)


class AnimalPhoto(Base):
    __tablename__ = "animal_photos"

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    animal_id: Mapped[int] = mapped_column(
        BigInteger, ForeignKey("animals.id", ondelete="CASCADE"), nullable=False, index=True
    )
    url: Mapped[str] = mapped_column(String(500), nullable=False)

    created_at: Mapped[datetime] = mapped_column(TIMESTAMP(timezone=False), server_default=func.now())


class Animal(Base):
    __tablename__ = "animals"

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    species_id: Mapped[int] = mapped_column(
        BigInteger, ForeignKey("species.id", ondelete="RESTRICT"), nullable=False, index=True
    )
    # Producto gemelo: el animal se vende por el POS a través de este producto
    product_id: Mapped[int] = mapped_column(
        BigInteger, ForeignKey("products.id", ondelete="RESTRICT"), nullable=False, unique=True
    )

    code: Mapped[str] = mapped_column(String(50), nullable=False, unique=True)
    # ponytail: enums como String + validación Pydantic; enum nativo de PG si algún día hace falta
    sex: Mapped[str] = mapped_column(String(10), nullable=False, server_default="unknown")
    status: Mapped[str] = mapped_column(String(20), nullable=False, server_default="available", index=True)

    birth_date: Mapped[Optional[date]] = mapped_column(Date, nullable=True)
    price: Mapped[Decimal] = mapped_column(Numeric(12, 2), nullable=False)
    # Precio anterior (tachado) para mostrar oferta en la tienda
    compare_at_price: Mapped[Optional[Decimal]] = mapped_column(Numeric(12, 2), nullable=True)
    price_cost: Mapped[Decimal] = mapped_column(Numeric(12, 2), nullable=False, server_default="0")
    description: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    image: Mapped[Optional[str]] = mapped_column(String(250), nullable=True)

    # Documentación legal (SEMARNAT/UMA); opcional — no todos los animales la requieren
    requires_legal_doc: Mapped[bool] = mapped_column(Boolean, nullable=False, server_default="0")
    legal_doc: Mapped[Optional[str]] = mapped_column(String(150), nullable=True)
    legal_doc_url: Mapped[Optional[str]] = mapped_column(String(500), nullable=True)

    created_at: Mapped[datetime] = mapped_column(TIMESTAMP(timezone=False), server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(
        TIMESTAMP(timezone=False), server_default=func.now(), onupdate=func.now()
    )

    species = relationship("Species", back_populates="animals")
    product = relationship("Product")
    morphs: Mapped[list["Morph"]] = relationship("Morph", secondary=animal_has_morphs)

    @property
    def stock(self) -> Optional[int]:
        """Unidades disponibles = stock del producto gemelo (individuales: 1).

        Las especies en cepa/paquete usan un solo registro con lote de N;
        la venta descuenta el lote y el animal pasa a sold al llegar a 0.
        """
        if self.product is None:
            return None
        return int(sum(b.quantity for b in self.product.batches))
    photos: Mapped[list["AnimalPhoto"]] = relationship(
        "AnimalPhoto", cascade="all, delete-orphan", order_by="AnimalPhoto.id"
    )
