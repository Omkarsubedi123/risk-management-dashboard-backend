from django.db import models
from projects.models import Project

class Risk(models.Model):
    project = models.ForeignKey(
        "projects.Project",
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
    calculated_loss = models.DecimalField(max_digits=12, decimal_places=2, blank=True, null=True)

    risk_decision = models.CharField(max_length=30)
    assigned_to = models.CharField(max_length=100)

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
