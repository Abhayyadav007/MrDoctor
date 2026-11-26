from django.urls import path
from .views import (AddVisitView, CaseCreateView, CaseDetailView, CaseListView, CasePDFView,
                    CaseUpdateView, DownloadAttachmentView, PatientHistoryView, UploadAttachmentView)

urlpatterns = [
    path("", CaseListView.as_view(), name="case_list"),
    path("new/", CaseCreateView.as_view(), name="case_create"),
    path("attachments/<int:pk>/download/", DownloadAttachmentView.as_view(), name="attachment_download"),
    path("<int:pk>/", CaseDetailView.as_view(), name="case_detail"),
    path("<int:pk>/visit/", AddVisitView.as_view(), name="add_visit"),
    path("<int:pk>/update/", CaseUpdateView.as_view(), name="case_update"),
    path("<int:pk>/upload/", UploadAttachmentView.as_view(), name="case_upload"),
    path("<int:pk>/pdf/", CasePDFView.as_view(), name="case_pdf"),
    path("patient/<int:patient_id>/history/", PatientHistoryView.as_view(), name="patient_history"),
]
