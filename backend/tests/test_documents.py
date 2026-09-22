import os
import pytest
from models.db import db, Driver


@pytest.fixture()
def driver_with_docs(app, vehicle):
    upload_folder = app.config["UPLOAD_FOLDER"]
    os.makedirs(upload_folder, exist_ok=True)

    # Sample binary contents
    pdf_content = b"%PDF-1.4\n1 0 obj\n<< /Type /Catalog >>\nendobj\ntrailer\n<< /Root 1 0 R >>\n%%EOF"
    jpg_content = b"\xff\xd8\xff\xe0\x00\x10JFIF\x00\x01\x01\x01\x00H\x00H\x00\x00\xff\xdb"
    png_content = b"\x89PNG\r\n\x1a\n\x00\x00\x00\rIHDR\x00\x00\x00\x01\x00\x00\x00\x01\x08\x06\x00\x00\x00\x1f\x15c4"
    webp_content = b"RIFF\x24\x00\x00\x00WEBPVP8 \x18\x00\x00\x000\x01\x00\x9d\x01\x2a\x01\x00\x01\x00\x02\x00"

    pdf_filename = "testdriver_license_doc_license.pdf"
    jpg_filename = "testdriver_profile_photo_photo.jpg"
    png_filename = "testdriver_address_proof_address.png"
    webp_filename = "testdriver_doc_id.webp"
    no_ext_pdf_filename = "testdriver_raw_pdf_doc"

    with open(os.path.join(upload_folder, pdf_filename), "wb") as f:
        f.write(pdf_content)
    with open(os.path.join(upload_folder, jpg_filename), "wb") as f:
        f.write(jpg_content)
    with open(os.path.join(upload_folder, png_filename), "wb") as f:
        f.write(png_content)
    with open(os.path.join(upload_folder, webp_filename), "wb") as f:
        f.write(webp_content)
    with open(os.path.join(upload_folder, no_ext_pdf_filename), "wb") as f:
        f.write(pdf_content)

    with app.app_context():
        d = Driver(
            driver_code="D9999",
            name="Document Test Driver",
            username="docdriver",
            password_hash="hashedpass",
            email="docdriver@example.com",
            phone="9999988888",
            status="Pending",
            license_doc_path=pdf_filename,
            profile_photo_path=jpg_filename,
            address_proof_path=png_filename,
        )
        db.session.add(d)
        db.session.commit()
        return {
            "id": d.id,
            "pdf_filename": pdf_filename,
            "pdf_content": pdf_content,
            "jpg_filename": jpg_filename,
            "jpg_content": jpg_content,
            "png_filename": png_filename,
            "png_content": png_content,
            "webp_filename": webp_filename,
            "webp_content": webp_content,
            "no_ext_pdf_filename": no_ext_pdf_filename,
        }


class TestDocumentEndpoints:
    def test_get_driver_documents_list(self, client, admin_headers, driver_with_docs):
        r = client.get(f"/api/v1/admin/drivers/{driver_with_docs['id']}/documents", headers=admin_headers)
        assert r.status_code == 200
        docs = r.get_json()
        assert len(docs) == 3
        types = [d["type"] for d in docs]
        assert "license" in types
        assert "photo" in types
        assert "address" in types

    def test_serve_pdf_document(self, client, admin_headers, driver_with_docs):
        filename = driver_with_docs["pdf_filename"]
        r = client.get(f"/api/v1/admin/documents/{filename}", headers=admin_headers)
        assert r.status_code == 200
        assert r.headers.get("Content-Type") == "application/pdf"
        assert "inline" in r.headers.get("Content-Disposition", "")
        assert filename in r.headers.get("Content-Disposition", "")
        assert r.data == driver_with_docs["pdf_content"]

    def test_serve_jpeg_image(self, client, admin_headers, driver_with_docs):
        filename = driver_with_docs["jpg_filename"]
        r = client.get(f"/api/v1/admin/documents/{filename}", headers=admin_headers)
        assert r.status_code == 200
        assert r.headers.get("Content-Type") == "image/jpeg"
        assert "inline" in r.headers.get("Content-Disposition", "")
        assert filename in r.headers.get("Content-Disposition", "")
        assert r.data == driver_with_docs["jpg_content"]

    def test_serve_png_image(self, client, admin_headers, driver_with_docs):
        filename = driver_with_docs["png_filename"]
        r = client.get(f"/api/v1/admin/documents/{filename}", headers=admin_headers)
        assert r.status_code == 200
        assert r.headers.get("Content-Type") == "image/png"
        assert "inline" in r.headers.get("Content-Disposition", "")
        assert filename in r.headers.get("Content-Disposition", "")
        assert r.data == driver_with_docs["png_content"]

    def test_serve_webp_image(self, client, admin_headers, driver_with_docs):
        filename = driver_with_docs["webp_filename"]
        r = client.get(f"/api/v1/admin/documents/{filename}", headers=admin_headers)
        assert r.status_code == 200
        assert r.headers.get("Content-Type") == "image/webp"
        assert "inline" in r.headers.get("Content-Disposition", "")
        assert filename in r.headers.get("Content-Disposition", "")
        assert r.data == driver_with_docs["webp_content"]

    def test_serve_document_magic_byte_sniffing(self, client, admin_headers, driver_with_docs):
        filename = driver_with_docs["no_ext_pdf_filename"]
        r = client.get(f"/api/v1/admin/documents/{filename}", headers=admin_headers)
        assert r.status_code == 200
        # Magic bytes '%PDF-' detected as application/pdf even with no file extension
        assert r.headers.get("Content-Type") == "application/pdf"
        assert "inline" in r.headers.get("Content-Disposition", "")
        assert r.data == driver_with_docs["pdf_content"]

    def test_serve_missing_document_404(self, client, admin_headers):
        r = client.get("/api/v1/admin/documents/non_existent_file.pdf", headers=admin_headers)
        assert r.status_code == 404
        assert r.get_json()["code"] == "NOT_FOUND"

    def test_serve_document_unauthenticated_401(self, client, driver_with_docs):
        filename = driver_with_docs["pdf_filename"]
        r = client.get(f"/api/v1/admin/documents/{filename}")
        assert r.status_code == 401

    def test_serve_document_unauthorized_role_403(self, client, driver_headers, driver_with_docs):
        filename = driver_with_docs["pdf_filename"]
        r = client.get(f"/api/v1/admin/documents/{filename}", headers=driver_headers)
        assert r.status_code == 403
