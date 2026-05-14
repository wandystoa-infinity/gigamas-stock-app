from app import app
from models.models import db, User, Cabang


with app.app_context():

    # =========================================
    # CEK SUPER ADMIN
    # =========================================
    existing_admin = User.query.filter_by(
        username="admin"
    ).first()

    if existing_admin:
        print("Super admin sudah ada.")
        exit()


    # =========================================
    # BUAT CABANG PUSAT
    # =========================================
    cabang_pusat = Cabang.query.filter_by(
        nama_cabang="PUSAT"
    ).first()

    if not cabang_pusat:

        cabang_pusat = Cabang(
            nama_cabang="PUSAT",
            alamat="Kantor Pusat Gigamas",
            kontak="08123456789",
            is_active=True
        )

        db.session.add(cabang_pusat)
        db.session.commit()

        print("Cabang pusat berhasil dibuat.")


    # =========================================
    # BUAT SUPER ADMIN
    # =========================================
    admin = User(
        username="admin",
        nama_lengkap="Super Admin Gigamas",
        role="super_admin",
        cabang_id=None,
        nomor_whatsapp="628123456789",
        menerima_alert=True,
        status_aktif=True
    )

    admin.set_password("admin123")

    db.session.add(admin)
    db.session.commit()

    print("===================================")
    print("SUPER ADMIN BERHASIL DIBUAT")
    print("===================================")
    print("Username : admin")
    print("Password : admin123")
    print("Role     : super_admin")
    print("===================================")