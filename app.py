from flask import (
    Flask,
    render_template,
    request,
    redirect,
    url_for,
    flash,
    abort,
    jsonify,
    send_file,
    make_response
)

from flask_login import (
    LoginManager,
    login_user,
    logout_user,
    login_required,
    current_user
)

from flask_migrate import Migrate
from sqlalchemy import func
from functools import wraps
from datetime import datetime, date, timedelta
import os
import json
import requests

from config import Config
from io import BytesIO
from openpyxl import Workbook

from models.models import (
    db,
    Cabang,
    Supplier,
    Barang,
    StockCabang,
    Transaksi,
    User,
    WhatsAppAlertLog
)

from reportlab.lib.pagesizes import A4
from reportlab.lib import colors
from reportlab.lib.units import cm

from reportlab.platypus import (
    SimpleDocTemplate,
    Table,
    TableStyle,
    Paragraph,
    Spacer,
    Image
)

from reportlab.lib.styles import (
    getSampleStyleSheet,
    ParagraphStyle
)



# =========================================================
# APP INIT
# =========================================================
app = Flask(__name__)
app.config.from_object(Config)

db.init_app(app)
migrate = Migrate(app, db)


# =========================================================
# LOGIN MANAGER
# =========================================================
login_manager = LoginManager()
login_manager.init_app(app)
login_manager.login_view = "login"
login_manager.login_message = "Silakan login terlebih dahulu."
login_manager.login_message_category = "warning"


@login_manager.user_loader
def load_user(user_id):
    return db.session.get(User, int(user_id))


# =========================================================
# ROLE CONFIG
# =========================================================
ROLE_SUPER_ADMIN = "super_admin"
ROLE_ADMIN_CABANG = "admin_cabang"
ROLE_OPERATOR = "operator_gudang"
ROLE_VIEWER = "viewer"

ROLE_CAN_INPUT_TRANSAKSI = [
    ROLE_SUPER_ADMIN,
    ROLE_ADMIN_CABANG,
    ROLE_OPERATOR
]

ROLE_CAN_VIEW_LAPORAN = [
    ROLE_SUPER_ADMIN,
    ROLE_ADMIN_CABANG,
    ROLE_VIEWER
]


# =========================================================
# DECORATORS
# =========================================================
def role_required(*roles):
    def decorator(func_route):
        @wraps(func_route)
        def wrapper(*args, **kwargs):
            if not current_user.is_authenticated:
                return redirect(url_for("login"))

            if current_user.role not in roles:
                abort(403)

            return func_route(*args, **kwargs)
        return wrapper
    return decorator


def super_admin_required(func_route):
    @wraps(func_route)
    def wrapper(*args, **kwargs):
        if not current_user.is_authenticated:
            return redirect(url_for("login"))

        if current_user.role != ROLE_SUPER_ADMIN:
            abort(403)

        return func_route(*args, **kwargs)
    return wrapper


# =========================================================
# HELPER ROLE / CABANG
# =========================================================
def get_current_cabang_id():
    if current_user.role == ROLE_SUPER_ADMIN:
        cabang_id = request.args.get("cabang_id", type=int)
        return cabang_id

    return current_user.cabang_id


def get_allowed_cabang_query():
    if current_user.role == ROLE_SUPER_ADMIN:
        return Cabang.query.filter_by(is_active=True).order_by(Cabang.nama_cabang.asc())

    return Cabang.query.filter(
        Cabang.id == current_user.cabang_id,
        Cabang.is_active == True
    )


def user_can_access_cabang(cabang_id):
    if current_user.role == ROLE_SUPER_ADMIN:
        return True

    return current_user.cabang_id == cabang_id


# =========================================================
# WHATSAPP ALERT HELPER
# =========================================================
def kirim_whatsapp_asli(nomor_tujuan, pesan):

    access_token = os.getenv("WHATSAPP_ACCESS_TOKEN")
    phone_number_id = os.getenv("WHATSAPP_PHONE_NUMBER_ID")
    api_version = os.getenv("WHATSAPP_API_VERSION", "v20.0")

    url = f"https://graph.facebook.com/{api_version}/{phone_number_id}/messages"

    headers = {
        "Authorization": f"Bearer {access_token}",
        "Content-Type": "application/json"
    }

    payload = {
        "messaging_product": "whatsapp",
        "to": nomor_tujuan,
        "type": "text",
        "text": {
            "body": pesan
        }
    }

    try:
        response = requests.post(
            url,
            headers=headers,
            json=payload,
            timeout=30
        )

        response_json = response.json()

        print("WHATSAPP RESPONSE:")
        print(response_json)

        if response.status_code in [200, 201]:
            return True, json.dumps(response_json)

        return False, json.dumps(response_json)

    except Exception as e:
        return False, str(e)


def buat_log_whatsapp(
    kategori_alert,
    pesan,
    cabang_id=None,
    barang_id=None,
    transaksi_id=None
):
    penerima = User.query.filter(
        User.menerima_alert == True,
        User.nomor_whatsapp.isnot(None),
        User.status_aktif == True
    )

    if cabang_id:
        penerima = penerima.filter(
            (User.role == ROLE_SUPER_ADMIN) |
            (User.cabang_id == cabang_id)
        )

    penerima = penerima.all()

    for user in penerima:
        log = WhatsAppAlertLog(
            nomor_tujuan=user.nomor_whatsapp,
            nama_tujuan=user.nama_lengkap,
            kategori_alert=kategori_alert,
            pesan=pesan,
            status="pending",
            transaksi_id=transaksi_id,
            cabang_id=cabang_id,
            barang_id=barang_id
        )

        db.session.add(log)
        db.session.flush()

        sukses, hasil = kirim_whatsapp_asli(
            user.nomor_whatsapp,
            pesan
        )

        if sukses:
            log.status = "sent"
            log.response_api = hasil
            log.sent_at = datetime.now()
        else:
            log.status = "failed"
            log.response_api = hasil

    db.session.commit()


def cek_alert_stok(stock_data):
    barang = stock_data.barang
    cabang = stock_data.cabang

    if barang.stok_kritis is not None and stock_data.stock <= barang.stok_kritis:
        pesan = (
            f"🚨 ALERT STOK KRITIS GIGAMAS\n\n"
            f"Cabang: {cabang.nama_cabang}\n"
            f"Barang: {barang.nama_barang}\n"
            f"Stok Saat Ini: {stock_data.stock} {barang.satuan}\n"
            f"Batas Kritis: {barang.stok_kritis} {barang.satuan}\n\n"
            f"Segera lakukan pengecekan dan pengadaan barang."
        )

        buat_log_whatsapp(
            kategori_alert="stok_kritis",
            pesan=pesan,
            cabang_id=cabang.id,
            barang_id=barang.id
        )

    elif barang.stok_minimum is not None and stock_data.stock <= barang.stok_minimum:
        pesan = (
            f"⚠️ ALERT STOK MENIPIS GIGAMAS\n\n"
            f"Cabang: {cabang.nama_cabang}\n"
            f"Barang: {barang.nama_barang}\n"
            f"Stok Saat Ini: {stock_data.stock} {barang.satuan}\n"
            f"Batas Minimum: {barang.stok_minimum} {barang.satuan}\n\n"
            f"Disarankan segera tambah stok."
        )

        buat_log_whatsapp(
            kategori_alert="stok_menipis",
            pesan=pesan,
            cabang_id=cabang.id,
            barang_id=barang.id
        )


def cek_alert_barang_keluar_besar(transaksi):
    batas_besar = int(os.getenv("BATAS_BARANG_KELUAR_BESAR", 100))

    if transaksi.jenis == "keluar" and transaksi.jumlah >= batas_besar:
        pesan = (
            f"📦 ALERT BARANG KELUAR BESAR GIGAMAS\n\n"
            f"Cabang: {transaksi.cabang.nama_cabang}\n"
            f"Barang: {transaksi.barang.nama_barang}\n"
            f"Jumlah Keluar: {transaksi.jumlah} {transaksi.barang.satuan}\n"
            f"Operator: {transaksi.user.nama_lengkap}\n"
            f"Tanggal: {transaksi.tanggal}\n\n"
            f"Mohon dilakukan pengecekan transaksi."
        )

        buat_log_whatsapp(
            kategori_alert="barang_keluar_besar",
            pesan=pesan,
            cabang_id=transaksi.cabang_id,
            barang_id=transaksi.barang_id,
            transaksi_id=transaksi.id
        )


# =========================================================
# ROOT
# =========================================================
@app.route("/")
@login_required
def root():
    return redirect(url_for("dashboard"))


# =========================================================
# AUTH
# =========================================================
@app.route("/login", methods=["GET", "POST"])
def login():
    if current_user.is_authenticated:
        return redirect(url_for("dashboard"))

    if request.method == "POST":
        username = request.form.get("username")
        password = request.form.get("password")

        user = User.query.filter_by(username=username).first()

        if not user:
            flash("Username tidak ditemukan.", "danger")
            return redirect(url_for("login"))

        if not user.status_aktif:
            flash("Akun Anda tidak aktif.", "danger")
            return redirect(url_for("login"))

        if not user.check_password(password):
            flash("Password salah.", "danger")
            return redirect(url_for("login"))

        login_user(user)
        flash("Login berhasil.", "success")
        return redirect(url_for("dashboard"))

    return render_template("login.html")


@app.route("/logout")
@login_required
def logout():
    logout_user()
    flash("Anda berhasil logout.", "success")
    return redirect(url_for("login"))


# =========================================================
# DASHBOARD
# =========================================================
@app.route("/dashboard")
@login_required
def dashboard():
    cabang_id = get_current_cabang_id()

    cabang_list = get_allowed_cabang_query().all()

    stock_query = StockCabang.query.join(Barang).join(Cabang)

    transaksi_query = Transaksi.query.join(Barang).join(Cabang)

    if cabang_id:
        stock_query = stock_query.filter(StockCabang.cabang_id == cabang_id)
        transaksi_query = transaksi_query.filter(Transaksi.cabang_id == cabang_id)
    elif current_user.role != ROLE_SUPER_ADMIN:
        stock_query = stock_query.filter(StockCabang.cabang_id == current_user.cabang_id)
        transaksi_query = transaksi_query.filter(Transaksi.cabang_id == current_user.cabang_id)

    today = date.today()

    total_barang = Barang.query.filter_by(is_active=True).count()

    total_stock = stock_query.with_entities(
        func.coalesce(func.sum(StockCabang.stock), 0)
    ).scalar()

    barang_masuk_hari_ini = transaksi_query.filter(
        Transaksi.jenis == "masuk",
        func.date(Transaksi.tanggal) == today
    ).with_entities(
        func.coalesce(func.sum(Transaksi.jumlah), 0)
    ).scalar()

    barang_keluar_hari_ini = transaksi_query.filter(
        Transaksi.jenis == "keluar",
        func.date(Transaksi.tanggal) == today
    ).with_entities(
        func.coalesce(func.sum(Transaksi.jumlah), 0)
    ).scalar()

    stok_menipis = stock_query.filter(
    StockCabang.stock <= Barang.stok_minimum
    ).count()

    stok_per_cabang = db.session.query(
        Cabang.nama_cabang,
        func.coalesce(func.sum(StockCabang.stock), 0)
    ).join(
        StockCabang,
        StockCabang.cabang_id == Cabang.id
    ).group_by(
        Cabang.nama_cabang
    ).all()

    if current_user.role != ROLE_SUPER_ADMIN:
        stok_per_cabang = [
            row for row in stok_per_cabang
            if row[0] == current_user.cabang.nama_cabang
        ]

    top_barang_keluar = transaksi_query.filter(
        Transaksi.jenis == "keluar"
    ).with_entities(
        Barang.nama_barang,
        func.coalesce(func.sum(Transaksi.jumlah), 0).label("total_keluar")
    ).group_by(
        Barang.nama_barang
    ).order_by(
        func.sum(Transaksi.jumlah).desc()
    ).limit(5).all()

    tujuh_hari_lalu = datetime.now() - timedelta(days=7)

    trend_transaksi = transaksi_query.filter(
        Transaksi.tanggal >= tujuh_hari_lalu
    ).with_entities(
        func.date(Transaksi.tanggal).label("tanggal"),
        Transaksi.jenis,
        func.coalesce(func.sum(Transaksi.jumlah), 0).label("total")
    ).group_by(
        func.date(Transaksi.tanggal),
        Transaksi.jenis
    ).order_by(
        func.date(Transaksi.tanggal)
    ).all()

    transaksi_terbaru = transaksi_query.order_by(
        Transaksi.tanggal.desc()
    ).limit(10).all()

    return render_template(
        "dashboard.html",
        cabang_list=cabang_list,
        selected_cabang_id=cabang_id,
        total_barang=total_barang,
        total_stock=total_stock,
        barang_masuk_hari_ini=barang_masuk_hari_ini,
        barang_keluar_hari_ini=barang_keluar_hari_ini,
        stok_menipis=stok_menipis,
        stok_per_cabang=stok_per_cabang,
        top_barang_keluar=top_barang_keluar,
        trend_transaksi=trend_transaksi,
        transaksi_terbaru=transaksi_terbaru
    )


# =========================================================
# MASTER BARANG
# =========================================================
@app.route("/barang")
@login_required
def barang():
    data_barang = Barang.query.order_by(Barang.nama_barang.asc()).all()
    return render_template("barang.html", data_barang=data_barang)


@app.route("/barang/tambah", methods=["POST"])
@login_required
@role_required(ROLE_SUPER_ADMIN)
def tambah_barang():
    nama_barang = request.form.get("nama_barang")
    kategori = request.form.get("kategori")
    satuan = request.form.get("satuan")
    stok_minimum = request.form.get("stok_minimum", type=int) or 0
    stok_kritis = request.form.get("stok_kritis", type=int) or 0

    barang_baru = Barang(
        nama_barang=nama_barang,
        kategori=kategori,
        satuan=satuan,
        stok_minimum=stok_minimum,
        stok_kritis=stok_kritis,
        is_active=True
    )

    db.session.add(barang_baru)
    db.session.commit()

    flash("Barang berhasil ditambahkan.", "success")
    return redirect(url_for("barang"))


@app.route("/barang/edit/<int:id>", methods=["POST"])
@login_required
@role_required(ROLE_SUPER_ADMIN)
def edit_barang(id):
    barang_data = Barang.query.get_or_404(id)

    barang_data.nama_barang = request.form.get("nama_barang")
    barang_data.kategori = request.form.get("kategori")
    barang_data.satuan = request.form.get("satuan")
    barang_data.stok_minimum = request.form.get("stok_minimum", type=int) or 0
    barang_data.stok_kritis = request.form.get("stok_kritis", type=int) or 0

    db.session.commit()

    flash("Barang berhasil diperbarui.", "success")
    return redirect(url_for("barang"))


@app.route("/barang/hapus/<int:id>")
@login_required
@role_required(ROLE_SUPER_ADMIN)
def hapus_barang(id):
    barang_data = Barang.query.get_or_404(id)
    barang_data.is_active = False
    db.session.commit()

    flash("Barang berhasil dinonaktifkan.", "success")
    return redirect(url_for("barang"))


# =========================================================
# SUPPLIER
# =========================================================
@app.route("/supplier")
@login_required
def supplier():
    data_supplier = Supplier.query.order_by(Supplier.nama_supplier.asc()).all()
    return render_template("supplier.html", data_supplier=data_supplier)


@app.route("/supplier/tambah", methods=["POST"])
@login_required
@role_required(ROLE_SUPER_ADMIN)
def tambah_supplier():
    supplier_baru = Supplier(
        nama_supplier=request.form.get("nama_supplier"),
        kontak=request.form.get("kontak"),
        alamat=request.form.get("alamat"),
        is_active=True
    )

    db.session.add(supplier_baru)
    db.session.commit()

    flash("Supplier berhasil ditambahkan.", "success")
    return redirect(url_for("supplier"))


@app.route("/supplier/edit/<int:id>", methods=["POST"])
@login_required
@role_required(ROLE_SUPER_ADMIN)
def edit_supplier(id):
    supplier_data = Supplier.query.get_or_404(id)

    supplier_data.nama_supplier = request.form.get("nama_supplier")
    supplier_data.kontak = request.form.get("kontak")
    supplier_data.alamat = request.form.get("alamat")

    db.session.commit()

    flash("Supplier berhasil diperbarui.", "success")
    return redirect(url_for("supplier"))


@app.route("/supplier/hapus/<int:id>")
@login_required
@role_required(ROLE_SUPER_ADMIN)
def hapus_supplier(id):
    supplier_data = Supplier.query.get_or_404(id)
    supplier_data.is_active = False

    db.session.commit()

    flash("Supplier berhasil dinonaktifkan.", "success")
    return redirect(url_for("supplier"))


# =========================================================
# CABANG
# =========================================================
@app.route("/cabang")
@login_required
@role_required(ROLE_SUPER_ADMIN)
def cabang():
    data_cabang = Cabang.query.order_by(Cabang.nama_cabang.asc()).all()
    return render_template("cabang.html", data_cabang=data_cabang)


@app.route("/cabang/tambah", methods=["POST"])
@login_required
@role_required(ROLE_SUPER_ADMIN)
def tambah_cabang():
    cabang_baru = Cabang(
        nama_cabang=request.form.get("nama_cabang"),
        alamat=request.form.get("alamat"),
        kontak=request.form.get("kontak"),
        is_active=True
    )

    db.session.add(cabang_baru)
    db.session.commit()

    flash("Cabang berhasil ditambahkan.", "success")
    return redirect(url_for("cabang"))


@app.route("/cabang/edit/<int:id>", methods=["POST"])
@login_required
@role_required(ROLE_SUPER_ADMIN)
def edit_cabang(id):
    cabang_data = Cabang.query.get_or_404(id)

    cabang_data.nama_cabang = request.form.get("nama_cabang")
    cabang_data.alamat = request.form.get("alamat")
    cabang_data.kontak = request.form.get("kontak")

    db.session.commit()

    flash("Cabang berhasil diperbarui.", "success")
    return redirect(url_for("cabang"))


@app.route("/cabang/hapus/<int:id>")
@login_required
@role_required(ROLE_SUPER_ADMIN)
def hapus_cabang(id):
    cabang_data = Cabang.query.get_or_404(id)
    cabang_data.is_active = False

    db.session.commit()

    flash("Cabang berhasil dinonaktifkan.", "success")
    return redirect(url_for("cabang"))


# =========================================================
# BARANG MASUK
# =========================================================
@app.route("/barang_masuk", methods=["GET", "POST"])
@login_required
@role_required(ROLE_SUPER_ADMIN, ROLE_ADMIN_CABANG, ROLE_OPERATOR)
def barang_masuk():
    barang_list = Barang.query.filter_by(is_active=True).order_by(Barang.nama_barang.asc()).all()
    supplier_list = Supplier.query.filter_by(is_active=True).order_by(Supplier.nama_supplier.asc()).all()
    cabang_list = get_allowed_cabang_query().all()

    if request.method == "POST":
        barang_id = request.form.get("barang_id", type=int)
        supplier_id = request.form.get("supplier_id", type=int)
        jumlah = request.form.get("jumlah", type=int)
        keterangan = request.form.get("keterangan")

        if current_user.role == ROLE_SUPER_ADMIN:
            cabang_id = request.form.get("cabang_id", type=int)
        else:
            cabang_id = current_user.cabang_id

        if not user_can_access_cabang(cabang_id):
            abort(403)

        if not barang_id or not cabang_id or not jumlah or jumlah <= 0:
            flash("Data barang masuk tidak valid.", "danger")
            return redirect(url_for("barang_masuk"))

        transaksi = Transaksi(
            barang_id=barang_id,
            cabang_id=cabang_id,
            supplier_id=supplier_id,
            created_by=current_user.id,
            jenis="masuk",
            jumlah=jumlah,
            keterangan=keterangan
        )

        stock_data = StockCabang.query.filter_by(
            barang_id=barang_id,
            cabang_id=cabang_id
        ).first()

        if not stock_data:
            stock_data = StockCabang(
                barang_id=barang_id,
                cabang_id=cabang_id,
                stock=0
            )
            db.session.add(stock_data)

        stock_data.stock += jumlah

        db.session.add(transaksi)
        db.session.commit()

        flash("Barang masuk berhasil disimpan.", "success")
        return redirect(url_for("barang_masuk"))

    transaksi_masuk = Transaksi.query.filter_by(jenis="masuk")

    if current_user.role != ROLE_SUPER_ADMIN:
        transaksi_masuk = transaksi_masuk.filter_by(cabang_id=current_user.cabang_id)

    transaksi_masuk = transaksi_masuk.order_by(Transaksi.tanggal.desc()).limit(50).all()

    return render_template(
        "barang_masuk.html",
        barang_list=barang_list,
        supplier_list=supplier_list,
        cabang_list=cabang_list,
        transaksi_masuk=transaksi_masuk
    )


# =========================================================
# BARANG KELUAR
# =========================================================
@app.route("/barang_keluar", methods=["GET", "POST"])
@login_required
@role_required(ROLE_SUPER_ADMIN, ROLE_ADMIN_CABANG, ROLE_OPERATOR)
def barang_keluar():
    barang_list = Barang.query.filter_by(is_active=True).order_by(Barang.nama_barang.asc()).all()
    cabang_list = get_allowed_cabang_query().all()

    if request.method == "POST":
        barang_id = request.form.get("barang_id", type=int)
        jumlah = request.form.get("jumlah", type=int)
        keterangan = request.form.get("keterangan")

        if current_user.role == ROLE_SUPER_ADMIN:
            cabang_id = request.form.get("cabang_id", type=int)
        else:
            cabang_id = current_user.cabang_id

        if not user_can_access_cabang(cabang_id):
            abort(403)

        if not barang_id or not cabang_id or not jumlah or jumlah <= 0:
            flash("Data barang keluar tidak valid.", "danger")
            return redirect(url_for("barang_keluar"))

        stock_data = StockCabang.query.filter_by(
            barang_id=barang_id,
            cabang_id=cabang_id
        ).first()

        if not stock_data or stock_data.stock < jumlah:
            flash("Stok tidak mencukupi.", "danger")
            return redirect(url_for("barang_keluar"))

        transaksi = Transaksi(
            barang_id=barang_id,
            cabang_id=cabang_id,
            supplier_id=None,
            created_by=current_user.id,
            jenis="keluar",
            jumlah=jumlah,
            keterangan=keterangan
        )

        stock_data.stock -= jumlah

        db.session.add(transaksi)
        db.session.commit()

        cek_alert_stok(stock_data)
        cek_alert_barang_keluar_besar(transaksi)

        flash("Barang keluar berhasil disimpan.", "success")
        return redirect(url_for("barang_keluar"))

    transaksi_keluar = Transaksi.query.filter_by(jenis="keluar")

    if current_user.role != ROLE_SUPER_ADMIN:
        transaksi_keluar = transaksi_keluar.filter_by(cabang_id=current_user.cabang_id)

    transaksi_keluar = transaksi_keluar.order_by(Transaksi.tanggal.desc()).limit(50).all()

    return render_template(
        "barang_keluar.html",
        barang_list=barang_list,
        cabang_list=cabang_list,
        transaksi_keluar=transaksi_keluar
    )


# =========================================================
# LAPORAN
# =========================================================
@app.route("/laporan")
@login_required
@role_required(ROLE_SUPER_ADMIN, ROLE_ADMIN_CABANG, ROLE_VIEWER)
def laporan():
    cabang_id = get_current_cabang_id()
    cabang_list = get_allowed_cabang_query().all()

    tanggal_mulai = request.args.get("tanggal_mulai")
    tanggal_selesai = request.args.get("tanggal_selesai")

    transaksi_query = Transaksi.query.join(Barang).join(Cabang)

    if cabang_id:
        transaksi_query = transaksi_query.filter(Transaksi.cabang_id == cabang_id)
    elif current_user.role != ROLE_SUPER_ADMIN:
        transaksi_query = transaksi_query.filter(Transaksi.cabang_id == current_user.cabang_id)

    if tanggal_mulai:
        transaksi_query = transaksi_query.filter(Transaksi.tanggal >= tanggal_mulai)

    if tanggal_selesai:
        transaksi_query = transaksi_query.filter(Transaksi.tanggal <= tanggal_selesai)

    transaksi_data = transaksi_query.order_by(Transaksi.tanggal.desc()).all()

    stock_query = StockCabang.query.join(Barang).join(Cabang)

    if cabang_id:
        stock_query = stock_query.filter(StockCabang.cabang_id == cabang_id)
    elif current_user.role != ROLE_SUPER_ADMIN:
        stock_query = stock_query.filter(StockCabang.cabang_id == current_user.cabang_id)

    data_stock = stock_query.order_by(Barang.nama_barang.asc()).all()

    grafik_stok_cabang = db.session.query(
        Cabang.nama_cabang,
        func.coalesce(func.sum(StockCabang.stock), 0).label("total_stock")
    ).join(
        StockCabang,
        StockCabang.cabang_id == Cabang.id
    ).group_by(
        Cabang.nama_cabang
    ).all()

    if current_user.role != ROLE_SUPER_ADMIN:
        grafik_stok_cabang = [
            row for row in grafik_stok_cabang
            if row[0] == current_user.cabang.nama_cabang
        ]

    grafik_masuk_keluar = transaksi_query.with_entities(
        func.date(Transaksi.tanggal).label("tanggal"),
        Transaksi.jenis,
        func.coalesce(func.sum(Transaksi.jumlah), 0).label("total")
    ).group_by(
        func.date(Transaksi.tanggal),
        Transaksi.jenis
    ).order_by(
        func.date(Transaksi.tanggal)
    ).all()

    grafik_barang_terlaris = transaksi_query.filter(
        Transaksi.jenis == "keluar"
    ).with_entities(
        Barang.nama_barang,
        func.coalesce(func.sum(Transaksi.jumlah), 0).label("total_keluar")
    ).group_by(
        Barang.nama_barang
    ).order_by(
        func.sum(Transaksi.jumlah).desc()
    ).limit(10).all()

    stok_menipis = stock_query.filter(
    StockCabang.stock <= Barang.stok_minimum
    ).all()

    return render_template(
        "laporan.html",
        cabang_list=cabang_list,
        selected_cabang_id=cabang_id,
        tanggal_mulai=tanggal_mulai,
        tanggal_selesai=tanggal_selesai,
        transaksi_data=transaksi_data,
        data_stock=data_stock,
        grafik_stok_cabang=grafik_stok_cabang,
        grafik_masuk_keluar=grafik_masuk_keluar,
        grafik_barang_terlaris=grafik_barang_terlaris,
        stok_menipis=stok_menipis
    )

@app.route("/export/excel")
@login_required
@role_required(ROLE_SUPER_ADMIN, ROLE_ADMIN_CABANG, ROLE_VIEWER)
def export_excel():

    cabang_id = get_current_cabang_id()

    query = Transaksi.query.join(Barang).join(Cabang)

    if cabang_id:
        query = query.filter(Transaksi.cabang_id == cabang_id)
    elif current_user.role != ROLE_SUPER_ADMIN:
        query = query.filter(Transaksi.cabang_id == current_user.cabang_id)

    data = query.order_by(Transaksi.tanggal.desc()).all()

    wb = Workbook()
    ws = wb.active
    ws.title = "Laporan Gigamas"

    headers = [
        "Tanggal",
        "Cabang",
        "Barang",
        "Jenis",
        "Jumlah",
        "Operator",
        "Keterangan"
    ]

    ws.append(headers)

    for trx in data:
        ws.append([
            trx.tanggal.strftime("%d-%m-%Y %H:%M"),
            trx.cabang.nama_cabang,
            trx.barang.nama_barang,
            trx.jenis,
            trx.jumlah,
            trx.user.nama_lengkap,
            trx.keterangan
        ])

    file_stream = BytesIO()
    wb.save(file_stream)
    file_stream.seek(0)

    return send_file(
        file_stream,
        as_attachment=True,
        download_name="laporan_gigamas.xlsx",
        mimetype="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
    )
@app.route("/export/pdf")
@login_required
@role_required(ROLE_SUPER_ADMIN, ROLE_ADMIN_CABANG, ROLE_VIEWER)
def export_pdf():

    cabang_id = get_current_cabang_id()
    tanggal_mulai = request.args.get("tanggal_mulai")
    tanggal_selesai = request.args.get("tanggal_selesai")

    query = Transaksi.query.join(Barang).join(Cabang)

    if cabang_id:
        query = query.filter(Transaksi.cabang_id == cabang_id)
    elif current_user.role != ROLE_SUPER_ADMIN:
        query = query.filter(Transaksi.cabang_id == current_user.cabang_id)

    if tanggal_mulai:
        query = query.filter(Transaksi.tanggal >= tanggal_mulai)

    if tanggal_selesai:
        query = query.filter(Transaksi.tanggal <= tanggal_selesai)

    data = query.order_by(Transaksi.tanggal.desc()).all()

    if cabang_id:
        cabang_data = Cabang.query.get(cabang_id)
        nama_cabang = cabang_data.nama_cabang if cabang_data else "-"
    else:
        nama_cabang = "Semua Cabang"

    total_transaksi = len(data)
    total_masuk = sum(trx.jumlah for trx in data if trx.jenis == "masuk")
    total_keluar = sum(trx.jumlah for trx in data if trx.jenis == "keluar")

    periode = "Semua Periode"
    if tanggal_mulai and tanggal_selesai:
        periode = f"{tanggal_mulai} s/d {tanggal_selesai}"
    elif tanggal_mulai:
        periode = f"Mulai {tanggal_mulai}"
    elif tanggal_selesai:
        periode = f"Sampai {tanggal_selesai}"

    buffer = BytesIO()

    pdf = SimpleDocTemplate(
        buffer,
        pagesize=A4,
        rightMargin=1.2 * cm,
        leftMargin=1.2 * cm,
        topMargin=1.2 * cm,
        bottomMargin=1.2 * cm
    )

    styles = getSampleStyleSheet()

    title_style = ParagraphStyle(
        "GigamasTitle",
        parent=styles["Title"],
        fontSize=18,
        leading=22,
        textColor=colors.HexColor("#f97316"),
        alignment=1,
        spaceAfter=4
    )

    subtitle_style = ParagraphStyle(
        "GigamasSubtitle",
        parent=styles["Normal"],
        fontSize=10,
        leading=14,
        textColor=colors.HexColor("#444444"),
        alignment=1,
        spaceAfter=12
    )

    normal_style = ParagraphStyle(
        "GigamasNormal",
        parent=styles["Normal"],
        fontSize=9,
        leading=12,
        textColor=colors.HexColor("#111827")
    )

    small_style = ParagraphStyle(
        "GigamasSmall",
        parent=styles["Normal"],
        fontSize=8,
        leading=11,
        textColor=colors.HexColor("#6b7280")
    )

    elements = []

    logo_path = os.path.join(
        app.root_path,
        "static",
        "img",
        "logo_gigamas.png"
    )

    if os.path.exists(logo_path):
        logo = Image(
            logo_path,
            width=3.2 * cm,
            height=3.2 * cm
        )
    else:
        logo = Paragraph("", normal_style)

    header_text = [
        Paragraph(
        "LAPORAN TRANSAKSI GIGAMAS",
        title_style
        ),

        Paragraph(
        "Gizi Generasi Emas",
        subtitle_style
        )
    ]

    header_table = Table(
    [
        [logo, header_text]
    ],
    colWidths=[3 * cm, 13.8 * cm]
)

    header_table.setStyle(TableStyle([
        ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
        ("ALIGN", (0, 0), (0, 0), "CENTER"),
        ("ALIGN", (1, 0), (1, 0), "LEFT"),
        ("LEFTPADDING", (1, 0), (1, 0), 10),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 10),
    ]))

    elements.append(header_table)
    elements.append(Spacer(1, 8))

    info_data = [
        ["Tanggal Cetak", datetime.now().strftime("%d-%m-%Y %H:%M")],
        ["Cabang", nama_cabang],
        ["Periode", periode],
        ["Dicetak Oleh", current_user.nama_lengkap],
    ]

    info_table = Table(
        info_data,
        colWidths=[4.2 * cm, 12.2 * cm]
    )

    info_table.setStyle(TableStyle([
        ("BACKGROUND", (0, 0), (0, -1), colors.HexColor("#fff7ed")),
        ("TEXTCOLOR", (0, 0), (0, -1), colors.HexColor("#9a3412")),
        ("FONTNAME", (0, 0), (0, -1), "Helvetica-Bold"),
        ("FONTSIZE", (0, 0), (-1, -1), 9),
        ("GRID", (0, 0), (-1, -1), 0.4, colors.HexColor("#fed7aa")),
        ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 6),
        ("TOPPADDING", (0, 0), (-1, -1), 6),
    ]))

    elements.append(info_table)
    elements.append(Spacer(1, 12))

    summary_data = [
        ["Total Transaksi", "Total Barang Masuk", "Total Barang Keluar"],
        [str(total_transaksi), str(total_masuk), str(total_keluar)]
    ]

    summary_table = Table(
        summary_data,
        colWidths=[5.6 * cm, 5.6 * cm, 5.6 * cm]
    )

    summary_table.setStyle(TableStyle([
        ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#f97316")),
        ("TEXTCOLOR", (0, 0), (-1, 0), colors.white),
        ("FONTNAME", (0, 0), (-1, 0), "Helvetica-Bold"),
        ("FONTNAME", (0, 1), (-1, 1), "Helvetica-Bold"),
        ("FONTSIZE", (0, 0), (-1, 0), 9),
        ("FONTSIZE", (0, 1), (-1, 1), 14),
        ("ALIGN", (0, 0), (-1, -1), "CENTER"),
        ("GRID", (0, 0), (-1, -1), 0.4, colors.HexColor("#fed7aa")),
        ("BACKGROUND", (0, 1), (-1, 1), colors.HexColor("#fff7ed")),
        ("TEXTCOLOR", (0, 1), (-1, 1), colors.HexColor("#111827")),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 8),
        ("TOPPADDING", (0, 0), (-1, -1), 8),
    ]))

    elements.append(summary_table)
    elements.append(Spacer(1, 14))

    elements.append(Paragraph("Riwayat Transaksi", normal_style))
    elements.append(Spacer(1, 6))

    table_data = [[
        "No",
        "Tanggal",
        "Cabang",
        "Barang",
        "Jenis",
        "Jumlah",
        "Operator",
        "Keterangan"
    ]]

    for no, trx in enumerate(data, start=1):
        table_data.append([
            str(no),
            trx.tanggal.strftime("%d-%m-%Y %H:%M") if trx.tanggal else "-",
            trx.cabang.nama_cabang if trx.cabang else "-",
            trx.barang.nama_barang if trx.barang else "-",
            "Masuk" if trx.jenis == "masuk" else "Keluar",
            f"{trx.jumlah} {trx.barang.satuan if trx.barang else ''}",
            trx.user.nama_lengkap if trx.user else "-",
            trx.keterangan or "-"
        ])

    if len(table_data) == 1:
        table_data.append([
            "-",
            "-",
            "-",
            "-",
            "-",
            "-",
            "-",
            "Belum ada transaksi."
        ])

    table = Table(
        table_data,
        repeatRows=1,
        colWidths=[
            0.8 * cm,
            2.5 * cm,
            2.4 * cm,
            2.8 * cm,
            1.5 * cm,
            1.8 * cm,
            2.3 * cm,
            2.7 * cm
        ]
    )

    table.setStyle(TableStyle([
        ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#f97316")),
        ("TEXTCOLOR", (0, 0), (-1, 0), colors.white),
        ("FONTNAME", (0, 0), (-1, 0), "Helvetica-Bold"),
        ("FONTSIZE", (0, 0), (-1, 0), 7.5),
        ("FONTSIZE", (0, 1), (-1, -1), 6.8),
        ("ALIGN", (0, 0), (-1, -1), "CENTER"),
        ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
        ("GRID", (0, 0), (-1, -1), 0.35, colors.HexColor("#d1d5db")),
        ("ROWBACKGROUNDS", (0, 1), (-1, -1), [
            colors.white,
            colors.HexColor("#fff7ed")
        ]),
        ("BOTTOMPADDING", (0, 0), (-1, 0), 7),
        ("TOPPADDING", (0, 0), (-1, 0), 7),
    ]))

    elements.append(table)
    elements.append(Spacer(1, 18))

    elements.append(Paragraph(
        "Dokumen ini dibuat otomatis oleh Sistem Stock Management GIGAMAS.",
        small_style
    ))

    elements.append(Spacer(1, 30))

    tanda_tangan = Table(
        [
            ["", "Mengetahui,"],
            ["", ""],
            ["", ""],
            ["", "Admin Gigamas"],
        ],
        colWidths=[11 * cm, 5.5 * cm]
    )

    tanda_tangan.setStyle(TableStyle([
        ("ALIGN", (1, 0), (1, -1), "CENTER"),
        ("FONTSIZE", (0, 0), (-1, -1), 9),
        ("TEXTCOLOR", (0, 0), (-1, -1), colors.HexColor("#111827")),
    ]))

    elements.append(tanda_tangan)

    pdf.build(elements)

    buffer.seek(0)

    return send_file(
        buffer,
        as_attachment=True,
        download_name="laporan_gigamas.pdf",
        mimetype="application/pdf"
    )
@app.route("/whatsapp/kirim-pending")
@login_required
@role_required(ROLE_SUPER_ADMIN)
def kirim_pending_whatsapp():

    pending_logs = WhatsAppAlertLog.query.filter_by(
        status="pending"
    ).order_by(
        WhatsAppAlertLog.created_at.asc()
    ).limit(20).all()

    berhasil = 0
    gagal = 0

    for log in pending_logs:
        sukses, hasil = kirim_whatsapp_asli(
            log.nomor_tujuan,
            log.pesan
        )

        if sukses:
            log.status = "sent"
            log.response_api = hasil
            log.sent_at = datetime.now()
            berhasil += 1
        else:
            log.status = "failed"
            log.response_api = hasil
            gagal += 1

    db.session.commit()

    flash(
        f"Proses WhatsApp selesai. Berhasil: {berhasil}, Gagal: {gagal}",
        "success"
    )

    return redirect(url_for("dashboard"))
# =========================================================
# USER MANAGEMENT
# =========================================================
@app.route("/users")
@login_required
@role_required(ROLE_SUPER_ADMIN)
def users():
    data_user = User.query.order_by(User.nama_lengkap.asc()).all()
    cabang_list = Cabang.query.filter_by(is_active=True).order_by(Cabang.nama_cabang.asc()).all()

    return render_template(
        "users.html",
        data_user=data_user,
        cabang_list=cabang_list
    )


def format_nomor_whatsapp(nomor):
    if not nomor:
        return None

    nomor = nomor.strip().replace(" ", "").replace("-", "").replace("+", "")

    if nomor.startswith("0"):
        nomor = "62" + nomor[1:]

    return nomor


@app.route("/users/tambah", methods=["POST"])
@login_required
@role_required(ROLE_SUPER_ADMIN)
def tambah_user():
    username = request.form.get("username")
    password = request.form.get("password")
    nama_lengkap = request.form.get("nama_lengkap")
    role = request.form.get("role")
    cabang_id = request.form.get("cabang_id", type=int)
    nomor_whatsapp = format_nomor_whatsapp(request.form.get("nomor_whatsapp"))
    menerima_alert = True if request.form.get("menerima_alert") == "on" else False

    if role == ROLE_SUPER_ADMIN:
        cabang_id = None

    user_baru = User(
        username=username,
        nama_lengkap=nama_lengkap,
        role=role,
        cabang_id=cabang_id,
        nomor_whatsapp=nomor_whatsapp,
        menerima_alert=menerima_alert,
        status_aktif=True
    )

    user_baru.set_password(password)

    db.session.add(user_baru)
    db.session.commit()

    flash("User berhasil ditambahkan.", "success")
    return redirect(url_for("users"))


@app.route("/users/edit/<int:id>", methods=["POST"])
@login_required
@role_required(ROLE_SUPER_ADMIN)
def edit_user(id):
    user_data = User.query.get_or_404(id)

    user_data.nama_lengkap = request.form.get("nama_lengkap")
    user_data.username = request.form.get("username")
    user_data.role = request.form.get("role")

    cabang_id = request.form.get("cabang_id", type=int)

    if user_data.role == ROLE_SUPER_ADMIN:
        user_data.cabang_id = None
    else:
        user_data.cabang_id = cabang_id

    user_data.nomor_whatsapp = format_nomor_whatsapp(
        request.form.get("nomor_whatsapp")
    )

    user_data.menerima_alert = True if request.form.get("menerima_alert") == "on" else False

    password_baru = request.form.get("password")
    if password_baru:
        user_data.set_password(password_baru)

    db.session.commit()

    flash("User berhasil diperbarui.", "success")
    return redirect(url_for("users"))


@app.route("/users/nonaktif/<int:id>")
@login_required
@role_required(ROLE_SUPER_ADMIN)
def nonaktif_user(id):
    user_data = User.query.get_or_404(id)

    if user_data.id == current_user.id:
        flash("Akun sendiri tidak bisa dinonaktifkan.", "danger")
        return redirect(url_for("users"))

    user_data.status_aktif = False
    db.session.commit()

    flash("User berhasil dinonaktifkan.", "success")
    return redirect(url_for("users"))


@app.route("/users/delete/<int:id>")
@login_required
@role_required(ROLE_SUPER_ADMIN)
def delete_user(id):
    user_data = User.query.get_or_404(id)

    if user_data.id == current_user.id:
        flash("Tidak bisa menghapus akun sendiri.", "danger")
        return redirect(url_for("users"))

    jumlah_transaksi = Transaksi.query.filter_by(
        created_by=user_data.id
    ).count()

    if jumlah_transaksi > 0:
        user_data.status_aktif = False
        db.session.commit()

        flash(
            "User memiliki riwayat transaksi, sehingga tidak dihapus permanen. User dinonaktifkan.",
            "warning"
        )

        return redirect(url_for("users"))

    db.session.delete(user_data)
    db.session.commit()

    flash("User berhasil dihapus permanen.", "success")
    return redirect(url_for("users"))


# =========================================================
# API DATA CHART
# =========================================================
@app.route("/api/dashboard/chart")
@login_required
def api_dashboard_chart():
    cabang_id = get_current_cabang_id()

    transaksi_query = Transaksi.query

    if cabang_id:
        transaksi_query = transaksi_query.filter(Transaksi.cabang_id == cabang_id)
    elif current_user.role != ROLE_SUPER_ADMIN:
        transaksi_query = transaksi_query.filter(Transaksi.cabang_id == current_user.cabang_id)

    tujuh_hari_lalu = datetime.now() - timedelta(days=7)

    data = transaksi_query.filter(
        Transaksi.tanggal >= tujuh_hari_lalu
    ).with_entities(
        func.date(Transaksi.tanggal).label("tanggal"),
        Transaksi.jenis,
        func.coalesce(func.sum(Transaksi.jumlah), 0).label("total")
    ).group_by(
        func.date(Transaksi.tanggal),
        Transaksi.jenis
    ).order_by(
        func.date(Transaksi.tanggal)
    ).all()

    result = {}

    for row in data:
        tanggal_str = str(row.tanggal)

        if tanggal_str not in result:
            result[tanggal_str] = {
                "tanggal": tanggal_str,
                "masuk": 0,
                "keluar": 0
            }

        result[tanggal_str][row.jenis] = int(row.total)

    return jsonify(list(result.values()))


# =========================================================
# ERROR HANDLER
# =========================================================
@app.errorhandler(403)
def forbidden(error):
    return render_template("403.html"), 403


@app.errorhandler(404)
def not_found(error):
    return "Halaman tidak ditemukan.", 404


# =========================================================
# RUN
# =========================================================
if __name__ == "__main__":
    app.run(debug=True)