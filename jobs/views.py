from django.utils import timezone
from rest_framework import generics, permissions, status
from rest_framework.decorators import api_view, permission_classes
from rest_framework.response import Response

from accounts.models import DriverProfile
from .models import JobEngagement, JobStatusLog
from .serializers import JobEngagementSerializer, JobCreateSerializer


class IsClient(permissions.BasePermission):
    def has_permission(self, request, view):
        return request.user.role == "client"


class IsDriver(permissions.BasePermission):
    def has_permission(self, request, view):
        return request.user.role == "driver"


class JobListCreateView(generics.ListCreateAPIView):
    """Client: list own job engagements or post a new one."""

    permission_classes = [permissions.IsAuthenticated, IsClient]

    def get_serializer_class(self):
        if self.request.method == "POST":
            return JobCreateSerializer
        return JobEngagementSerializer

    def get_queryset(self):
        return JobEngagement.objects.filter(client=self.request.user)

    def perform_create(self, serializer):
        job = serializer.save(client=self.request.user)
        JobStatusLog.objects.create(
            job=job, status=JobEngagement.Status.OPEN, changed_by=self.request.user
        )
        from messaging.tasks import notify_drivers_of_new_job
        notify_drivers_of_new_job.delay(job.id)


class JobDetailView(generics.RetrieveAPIView):
    serializer_class = JobEngagementSerializer
    permission_classes = [permissions.IsAuthenticated]

    def get_queryset(self):
        user = self.request.user
        if user.role == "client":
            return JobEngagement.objects.filter(client=user)
        if user.role == "driver":
            return JobEngagement.objects.filter(driver=user)
        return JobEngagement.objects.all()


@api_view(["POST"])
@permission_classes([permissions.IsAuthenticated, IsDriver])
def accept_job(request, pk):
    try:
        job = JobEngagement.objects.get(pk=pk, status=JobEngagement.Status.OPEN)
    except JobEngagement.DoesNotExist:
        return Response({"detail": "Job not available."}, status=status.HTTP_404_NOT_FOUND)

    driver_profile = DriverProfile.objects.get(user=request.user)
    if driver_profile.status != "available":
        return Response({"detail": "You are not available."}, status=status.HTTP_400_BAD_REQUEST)

    job.driver = request.user
    job.status = JobEngagement.Status.HIRED
    job.hired_at = timezone.now()
    job.save()
    driver_profile.status = "busy"
    driver_profile.save()

    JobStatusLog.objects.create(job=job, status=JobEngagement.Status.HIRED, changed_by=request.user)
    return Response(JobEngagementSerializer(job).data)


@api_view(["POST"])
@permission_classes([permissions.IsAuthenticated, IsDriver])
def start_job(request, pk):
    try:
        job = JobEngagement.objects.get(pk=pk, driver=request.user, status=JobEngagement.Status.HIRED)
    except JobEngagement.DoesNotExist:
        return Response({"detail": "Job not found."}, status=status.HTTP_404_NOT_FOUND)

    job.status = JobEngagement.Status.ACTIVE
    job.started_at = timezone.now()
    job.save()
    JobStatusLog.objects.create(job=job, status=JobEngagement.Status.ACTIVE, changed_by=request.user)
    return Response(JobEngagementSerializer(job).data)


@api_view(["POST"])
@permission_classes([permissions.IsAuthenticated, IsDriver])
def end_job(request, pk):
    try:
        job = JobEngagement.objects.get(pk=pk, driver=request.user, status=JobEngagement.Status.ACTIVE)
    except JobEngagement.DoesNotExist:
        return Response({"detail": "Job not found."}, status=status.HTTP_404_NOT_FOUND)

    total_earned = request.data.get("total_earned")
    job.status = JobEngagement.Status.ENDED
    job.ended_at = timezone.now()
    if total_earned:
        job.total_earned = total_earned
    job.save()

    driver_profile = DriverProfile.objects.get(user=request.user)
    driver_profile.status = "available"
    driver_profile.total_jobs += 1
    driver_profile.save()

    JobStatusLog.objects.create(job=job, status=JobEngagement.Status.ENDED, changed_by=request.user)
    return Response(JobEngagementSerializer(job).data)


@api_view(["POST"])
@permission_classes([permissions.IsAuthenticated])
def cancel_job(request, pk):
    user = request.user
    qs = JobEngagement.objects.filter(pk=pk)
    if user.role == "client":
        qs = qs.filter(client=user, status__in=[JobEngagement.Status.OPEN, JobEngagement.Status.HIRED])
    elif user.role == "driver":
        qs = qs.filter(driver=user, status=JobEngagement.Status.HIRED)

    job = qs.first()
    if not job:
        return Response(
            {"detail": "Job not found or cannot be cancelled."},
            status=status.HTTP_404_NOT_FOUND,
        )

    job.status = JobEngagement.Status.CANCELLED
    job.save()

    if job.driver:
        dp = DriverProfile.objects.filter(user=job.driver).first()
        if dp:
            dp.status = "available"
            dp.save()

    JobStatusLog.objects.create(job=job, status=JobEngagement.Status.CANCELLED, changed_by=request.user)
    return Response(JobEngagementSerializer(job).data)


class OpenJobsView(generics.ListAPIView):
    """Driver: list all open job engagements available to accept."""

    serializer_class = JobEngagementSerializer
    permission_classes = [permissions.IsAuthenticated, IsDriver]

    def get_queryset(self):
        return JobEngagement.objects.filter(status=JobEngagement.Status.OPEN)
