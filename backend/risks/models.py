from django.db import models
from users.models import CustomUser
from projects.models import Project
from django.utils import timezone
from datetime import timedelta


class Risk(models.Model):

    # TM Mitigation Suggestion 

    tm_mitigation_suggestion = models.TextField(
        blank=True,
        help_text="Mitigation suggestion proposed by Team Member"
    )

    TM_SUGGESTION_STATUS_CHOICES = [
        ("pending", "Pending"),
        ("approved", "Approved"),
        ("rejected", "Rejected"),
    ]

    tm_suggestion_status = models.CharField(
        max_length=20,
        choices=TM_SUGGESTION_STATUS_CHOICES,
        default="pending"
    )


    APPROVAL_CHOICES = [
    ("pending", "Pending"),
    ("approved", "Approved"),
    ("rejected", "Rejected"),
]

    approval_status = models.CharField(
    max_length=20,
    choices=APPROVAL_CHOICES,
    default="approved",  # PM-created risks should be approved automatically
)
    rejected_at = models.DateTimeField(null=True, blank=True)
    approved_at = models.DateTimeField(null=True, blank=True)

    @property
    def is_in_trash(self):
        return self.approval_status == "rejected"

    @property
    def auto_delete_at(self):
        if self.rejected_at:
            return self.rejected_at + timedelta(days=15)
        return None

    RISK_DECISION_CHOICES = [
        ("Avoid", "Avoid"),
        ("Mitigate", "Mitigate"),
        ("Transfer", "Transfer"),
        ("Accept", "Accept"),
    ]

    STATUS_CHOICES = [
        ("Open", "Open"),
        ("InProgress", "In Progress"),
        ("Closed", "Closed"),
    ]

    MITIGATION_STATUS_CHOICES = [
        ("NotStarted", "Not Started"),
        ("InProgress", "In Progress"),
        ("Completed", "Completed"),
    ]

    LIKELIHOOD_CHOICES = [
        ("Low", "Low"),
        ("Medium", "Medium"),
        ("High", "High"),
    ]

    SEVERITY_CHOICES = [
        ("Low", "Low"),
        ("Medium", "Medium"),
        ("High", "High"),
    ]

    project = models.ForeignKey(
        Project,
        on_delete=models.CASCADE,
        related_name="risks"
    )

    created_by = models.ForeignKey(
        CustomUser,
        on_delete=models.SET_NULL,
        null=True,
        related_name="created_risks"
    )

    assigned_to = models.ForeignKey(
        CustomUser,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="assigned_risks"
    )

    title = models.CharField(max_length=255)
    description = models.TextField()

    probability = models.PositiveIntegerField()
    impact = models.PositiveIntegerField()

    risk_score = models.PositiveIntegerField(blank=True, null=True)
    likelihood = models.CharField(
        max_length=10,
        choices=LIKELIHOOD_CHOICES,
        blank=True,
        null=True
    )
    risk_level = models.CharField(
        max_length=10,
        choices=SEVERITY_CHOICES,
        blank=True,
        null=True
    )

    estimated_cost = models.DecimalField(
        max_digits=12,
        decimal_places=2,
        null=True,
        blank=True
    )

    risk_decision = models.CharField(
        max_length=20,
        choices=RISK_DECISION_CHOICES
    )

    status = models.CharField(
        max_length=20,
        choices=STATUS_CHOICES,
        default="Open"
    )

    mitigation_plan = models.TextField(blank=True)
    mitigation_status = models.CharField(
        max_length=20,
        choices=MITIGATION_STATUS_CHOICES,
        default="NotStarted"
    )

    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    def save(self, *args, **kwargs):
        self.risk_score = self.probability * self.impact

        if self.probability <= 2:
            self.likelihood = "Low"
        elif self.probability == 3:
            self.likelihood = "Medium"
        else:
            self.likelihood = "High"

        if self.risk_score <= 5:
            self.risk_level = "Low"
        elif self.risk_score <= 12:
            self.risk_level = "Medium"
        else:
            self.risk_level = "High"

        super().save(*args, **kwargs)

    def __str__(self):
        return self.title
