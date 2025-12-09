# eflab/admin.py
from django.contrib import admin
from django import forms
from .models import Survey, Question, Mark, Client, Answer
import csv
from django.http import HttpResponse
from .models import SurveyGift

# ----- Формы с нормальными виджетами -----
class SurveyForm(forms.ModelForm):
    class Meta:
        model = Survey
        fields = "__all__"
        widgets = {
            "description": forms.Textarea(attrs={"rows": 3}),
            "hello_text": forms.Textarea(attrs={"rows": 2}),
        }

class QuestionForm(forms.ModelForm):
    class Meta:
        model = Question
        fields = "__all__"
        widgets = {
            "que_text": forms.Textarea(attrs={"rows": 3, "style": "font-size:14px"}),
        }

class AnswerForm(forms.ModelForm):
    class Meta:
        model = Answer
        fields = "__all__"
        widgets = {
            "ans": forms.Textarea(attrs={"rows": 2}),
        }

# ----- Inlines -----
class MarkInline(admin.TabularInline):
    model = Mark
    extra = 1
    fields = ("mark_text",)
    show_change_link = True

class QuestionInline(admin.TabularInline):
    model = Question
    form = QuestionForm
    extra = 0
    fields = ("numb", "type_q", "que_text", "file", "kind_file")
    ordering = ("numb",)
    show_change_link = True

# ----- Admin классы -----
@admin.register(Survey)
class SurveyAdmin(admin.ModelAdmin):
    form = SurveyForm
    list_display = ("name", "slug", "active", "questions_count")
    list_filter = ("active",)
    search_fields = ("name", "slug", "description")
    prepopulated_fields = {"slug": ("name",)}
    inlines = [QuestionInline]
    fieldsets = (
        ("Основное", {"fields": ("name", "slug", "active")}),
        ("Описание", {"fields": ("description", "hello_text")}),
    )
    actions = ("activate", "deactivate")

    def questions_count(self, obj):
        return obj.question_set.count()
    questions_count.short_description = "Вопросов"

    @admin.action(description="Активировать выбранные")
    def activate(self, request, queryset):
        updated = queryset.update(active=True)
        self.message_user(request, f"Активировано: {updated}")

    @admin.action(description="Деактивировать выбранные")
    def deactivate(self, request, queryset):
        updated = queryset.update(active=False)
        self.message_user(request, f"Деактивировано: {updated}")


@admin.register(Question)
class QuestionAdmin(admin.ModelAdmin):
    form = QuestionForm
    list_display = ("survey", "numb", "type_q", "short_text", "has_file")
    list_filter = ("survey", "type_q", "kind_file")
    search_fields = ("que_text",)
    ordering = ("survey", "numb")
    inlines = [MarkInline]
    autocomplete_fields = ("survey",)
    fieldsets = (
        ("Привязка", {"fields": ("survey", "numb", "type_q")}),
        ("Текст и файл", {"fields": ("que_text", "file", "kind_file")}),
    )

    def short_text(self, obj):
        return (obj.que_text or "")[:60]
    short_text.short_description = "Текст"

    def has_file(self, obj):
        return bool(getattr(obj, "file", None))
    has_file.boolean = True
    has_file.short_description = "Файл?"


@admin.register(Mark)
class MarkAdmin(admin.ModelAdmin):
    list_display = ("que", "mark_text")
    search_fields = ("mark_text", "que__que_text")
    list_filter = ("que__survey",)
    autocomplete_fields = ("que",)


@admin.register(Client)
class ClientAdmin(admin.ModelAdmin):
    list_display = ("name", "acc_tg", "tg_id", "email", "phone")
    search_fields = ("name", "acc_tg", "tg_id", "email", "phone")
    list_per_page = 25
    ordering = ("name",)

def export_answers(modeladmin, request, queryset):
    response = HttpResponse(content_type="text/csv; charset=utf-8")
    response["Content-Disposition"] = 'attachment; filename="answers.csv"'
    writer = csv.writer(response)
    writer.writerow(["survey", "question_num", "question", "client", "telegram", "answer", "date"])
    for a in queryset.select_related("que__survey", "client_id"):
        writer.writerow([
            a.que.survey.name,
            a.que.numb,
            (a.que.que_text or "")[:120],
            getattr(a.client_id, "name", ""),
            a.client_tg_acc,
            (a.ans or "").replace("\n", " ")[:500],
            a.date,
        ])
    return response
export_answers.short_description = "Экспортировать выбранные ответы в CSV"


@admin.register(Answer)
class AnswerAdmin(admin.ModelAdmin):
    form = AnswerForm
    actions = (export_answers,)
    list_display = ("client_id", "survey_col", "question_col", "short_ans", "date")
    list_filter = ("que__survey", "date")
    search_fields = ("ans", "client_tg_acc", "client_id__name", "que__que_text")
    date_hierarchy = "date"
    autocomplete_fields = ("client_id", "que")
    readonly_fields = ("client_tg_acc", "date")

    def survey_col(self, obj):
        return obj.que.survey
    survey_col.short_description = "Опрос"

    def question_col(self, obj):
        return f"{obj.que.numb}. {obj.que.que_text[:40]}"
    question_col.short_description = "Вопрос"

    def short_ans(self, obj):
        txt = (obj.ans or "").replace("\n", " ")
        return (txt[:70] + "…") if len(txt) > 70 else txt
    short_ans.short_description = "Ответ"

@admin.register(SurveyGift)
class SurveyGiftAdmin(admin.ModelAdmin):
    list_display = ("survey", "file", "caption")
    list_filter = ("survey",)
    search_fields = ("survey__name", "caption")
    readonly_fields = ()
    fieldsets = (
        ("Опрос", {"fields": ("survey",)}),
        ("Подарок", {"fields": ("file", "caption")}),
    )

