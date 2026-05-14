from flask_sqlalchemy import SQLAlchemy
from sqlalchemy import func, UniqueConstraint
from werkzeug.security import generate_password_hash, check_password_hash
from flask_login import UserMixin

db = SQLAlchemy()


# ==========================================
# CABANG
# ==========================================
class Cabang(db.Model):
    __tablename__ = "cabang"

    id = db.Column(db.Integer, primary_key=True)
    nama_cabang = db.Column(db.String(150), nullable=False, unique=True)
    alamat = db.Column(db.Text)
    kontak = db.Column(db.String(100))
    is_active = db.Column(db.Boolean, default=True)

    created_at = db.Column(db.DateTime, server_default=func.now())
    updated_at = db.Column(
        db.DateTime,
        server_default=func.now(),
        onupdate=func.now()
    )

    users = db.relationship("User", backref="cabang", lazy=True)
    transaksi = db.relationship(
        "Transaksi",
        backref="cabang",
        lazy=True,
        cascade="all, delete-orphan"
    )
    stock_barang = db.relationship(
        "StockCabang",
        backref="cabang",
        lazy=True,
        cascade="all, delete-orphan"
    )

    def __repr__(self):
        return f"<Cabang {self.nama_cabang}>"


# ==========================================
# SUPPLIER
# ==========================================
class Supplier(db.Model):
    __tablename__ = "supplier"

    id = db.Column(db.Integer, primary_key=True)
    nama_supplier = db.Column(db.String(150), nullable=False, unique=True)
    kontak = db.Column(db.String(100))
    alamat = db.Column(db.Text)
    is_active = db.Column(db.Boolean, default=True)

    created_at = db.Column(db.DateTime, server_default=func.now())
    updated_at = db.Column(
        db.DateTime,
        server_default=func.now(),
        onupdate=func.now()
    )

    transaksi = db.relationship("Transaksi", backref="supplier", lazy=True)

    def __repr__(self):
        return f"<Supplier {self.nama_supplier}>"


# ==========================================
# BARANG
# ==========================================
class Barang(db.Model):
    __tablename__ = "barang"

    id = db.Column(db.Integer, primary_key=True)
    nama_barang = db.Column(db.String(150), nullable=False, unique=True)
    kategori = db.Column(db.String(100))
    satuan = db.Column(db.String(50), default="Kg")

    stok_minimum = db.Column(db.Integer, default=0)
    stok_kritis = db.Column(db.Integer, default=0)

    is_active = db.Column(db.Boolean, default=True)

    created_at = db.Column(db.DateTime, server_default=func.now())
    updated_at = db.Column(
        db.DateTime,
        server_default=func.now(),
        onupdate=func.now()
    )

    transaksi = db.relationship(
        "Transaksi",
        backref="barang",
        lazy=True,
        cascade="all, delete-orphan"
    )
    stock_cabang = db.relationship(
        "StockCabang",
        backref="barang",
        lazy=True,
        cascade="all, delete-orphan"
    )

    def __repr__(self):
        return f"<Barang {self.nama_barang}>"


# ==========================================
# STOCK CABANG
# ==========================================
class StockCabang(db.Model):
    __tablename__ = "stock_cabang"

    id = db.Column(db.Integer, primary_key=True)

    barang_id = db.Column(
        db.Integer,
        db.ForeignKey("barang.id"),
        nullable=False
    )
    cabang_id = db.Column(
        db.Integer,
        db.ForeignKey("cabang.id"),
        nullable=False
    )

    stock = db.Column(db.Integer, default=0, nullable=False)

    created_at = db.Column(db.DateTime, server_default=func.now())
    updated_at = db.Column(
        db.DateTime,
        server_default=func.now(),
        onupdate=func.now()
    )

    __table_args__ = (
        UniqueConstraint(
            "barang_id",
            "cabang_id",
            name="uix_barang_cabang"
        ),
    )

    def __repr__(self):
        return f"<StockCabang barang={self.barang_id} cabang={self.cabang_id} stock={self.stock}>"


# ==========================================
# TRANSAKSI
# ==========================================
class Transaksi(db.Model):
    __tablename__ = "transaksi"

    id = db.Column(db.Integer, primary_key=True)

    barang_id = db.Column(
        db.Integer,
        db.ForeignKey("barang.id"),
        nullable=False
    )
    cabang_id = db.Column(
        db.Integer,
        db.ForeignKey("cabang.id"),
        nullable=False
    )
    supplier_id = db.Column(
        db.Integer,
        db.ForeignKey("supplier.id"),
        nullable=True
    )

    created_by = db.Column(
        db.Integer,
        db.ForeignKey("users.id"),
        nullable=False
    )

    jenis = db.Column(db.String(20), nullable=False)
    jumlah = db.Column(db.Integer, nullable=False)
    keterangan = db.Column(db.Text)

    tanggal = db.Column(db.DateTime, server_default=func.now())

    user = db.relationship("User", backref="transaksi_user")

    def __repr__(self):
        return f"<Transaksi {self.jenis} jumlah={self.jumlah}>"


# ==========================================
# WHATSAPP ALERT LOG
# ==========================================
class WhatsAppAlertLog(db.Model):
    __tablename__ = "whatsapp_alert_log"

    id = db.Column(db.Integer, primary_key=True)

    nomor_tujuan = db.Column(db.String(50), nullable=False)
    nama_tujuan = db.Column(db.String(150))
    kategori_alert = db.Column(db.String(100), nullable=False)

    pesan = db.Column(db.Text, nullable=False)
    status = db.Column(db.String(50), default="pending")
    response_api = db.Column(db.Text)
    transaksi_id = db.Column(
        db.Integer,
        db.ForeignKey("transaksi.id"),
        nullable=True
    )
    cabang_id = db.Column(
        db.Integer,
        db.ForeignKey("cabang.id"),
        nullable=True
    )
    barang_id = db.Column(
        db.Integer,
        db.ForeignKey("barang.id"),
        nullable=True
    )

    created_at = db.Column(db.DateTime, server_default=func.now())
    sent_at = db.Column(db.DateTime)

    transaksi = db.relationship("Transaksi", backref="whatsapp_logs")
    cabang = db.relationship("Cabang", backref="whatsapp_logs")
    barang = db.relationship("Barang", backref="whatsapp_logs")

    def __repr__(self):
        return f"<WhatsAppAlertLog {self.kategori_alert} {self.status}>"


# ==========================================
# USER
# ==========================================
class User(UserMixin, db.Model):
    __tablename__ = "users"

    id = db.Column(db.Integer, primary_key=True)

    username = db.Column(db.String(100), unique=True, nullable=False)
    password = db.Column(db.String(255), nullable=False)
    nama_lengkap = db.Column(db.String(150), nullable=False)

    role = db.Column(db.String(50), default="viewer", nullable=False)
    status_aktif = db.Column(db.Boolean, default=True)

    cabang_id = db.Column(
        db.Integer,
        db.ForeignKey("cabang.id"),
        nullable=True
    )

    nomor_whatsapp = db.Column(db.String(50))
    menerima_alert = db.Column(db.Boolean, default=False)

    created_at = db.Column(db.DateTime, server_default=func.now())
    updated_at = db.Column(
        db.DateTime,
        server_default=func.now(),
        onupdate=func.now()
    )

    def set_password(self, password):
        self.password = generate_password_hash(password)

    def check_password(self, password):
        return check_password_hash(self.password, password)

    def is_super_admin(self):
        return self.role == "super_admin"

    def is_admin_cabang(self):
        return self.role == "admin_cabang"

    def is_operator(self):
        return self.role == "operator_gudang"

    def is_viewer(self):
        return self.role == "viewer"

    def can_manage_master(self):
        return self.role == "super_admin"

    def can_input_transaksi(self):
        return self.role in ["super_admin", "admin_cabang", "operator_gudang"]

    def can_view_laporan(self):
        return self.role in ["super_admin", "admin_cabang", "viewer"]

    def can_export_data(self):
        return self.role == "super_admin"

    def can_manage_user(self):
        return self.role == "super_admin"

    def __repr__(self):
        return f"<User {self.username} - {self.role}>"