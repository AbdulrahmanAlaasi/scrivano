from django.contrib import admin

from .models import (
    ActionItem,
    Commitment,
    Decision,
    DiscussionTopic,
    Question,
    Risk,
    SummarySection,
)

for model in (SummarySection, DiscussionTopic, Decision, ActionItem, Commitment, Question, Risk):
    admin.site.register(model)
