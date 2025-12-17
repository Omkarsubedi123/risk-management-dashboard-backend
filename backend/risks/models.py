from django.db import models
from django.conf import settings
from projects.models import Project

User = settings.AUTH_USER_MODEL


class Risk(models.Model):

    STATUS_CHOICES = [
        ("Open", "Open"),
        ("InProgress", "In Progress"),
        ("Closed", "Closed"),
    ]

    MITIGATION_STATUS_CHOICES = [
        ("NotStarted", "Not Started"),
        ("Ongoing", "Ongoing"),
        ("Completed", "Completed"),
    ]

    DECISION_CHOICES = [
        ("Avoid", "Avoid"),
        ("Mitigate", "Mitigate"),
        ("Transfer", "Transfer"),
        ("Accept", "Accept"),
    ]

    project = models.ForeignKey(
        Project,
        on_delete=models.CASCADE,
        related_name="risks"
    )

    title = models.CharField(max_length=255)
    description = models.TextField()

    impact = models.PositiveSmallIntegerField()
    probability = models.PositiveSmallIntegerField()

    risk_score = models.PositiveSmallIntegerField(blank=True, null=True)
    risk_level = models.CharField(max_length=20, blank=True)

    estimated_cost = models.DecimalField(max_digits=12, decimal_places=2)
    loss_percentage = models.PositiveSmallIntegerField()
    calculated_loss = models.DecimalField(
        max_digits=12, decimal_places=2, blank=True, null=True
    )

    risk_decision = models.CharField(
        max_length=20, choices=DECISION_CHOICES
    )

    status = models.CharField(
        max_length=20, choices=STATUS_CHOICES, default="Open"
    )

    mitigation_status = models.CharField(
        max_length=20,
        choices=MITIGATION_STATUS_CHOICES,
        default="NotStarted"
    )

    mitigation_plan = models.TextField(blank=True)

    assigned_to = models.ForeignKey(
        User,
        on_delete=models.SET_NULL,
        null=True,
        related_name="assigned_risks"
    )

    created_by = models.ForeignKey(
        User,
        on_delete=models.SET_NULL,
        null=True,
        related_name="created_risks"
    )

    created_at = models.DateTimeField(auto_now_add=True)

    def save(self, *args, **kwargs):
        self.risk_score = self.impact * self.probability

        if self.risk_score <= 5:
            self.risk_level = "Low"
        elif self.risk_score <= 10:
            self.risk_level = "Medium"
        elif self.risk_score <= 15:
            self.risk_level = "Medium-High"
        else:
            self.risk_level = "High"

        self.calculated_loss = (
            self.estimated_cost * self.loss_percentage / 100
        )

        super().save(*args, **kwargs)

    def __str__(self):
        return self.title
