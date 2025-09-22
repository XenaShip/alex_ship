from django.contrib import admin

from .models import Survey, Question, Answer, Client, Mark


@admin.register(Answer)
class AnswerAdmin(admin.ModelAdmin):
    list_display = ('que', 'ans', 'date')
    list_filter = ('que', 'ans', 'date')
    search_fields = ('que', 'ans', 'date')


@admin.register(Client)
class ClientAdmin(admin.ModelAdmin):
    list_display = ('name', 'acc_tg', 'email', 'phone')
    list_filter = ('name', 'acc_tg', 'email', 'phone')
    search_fields = ('name', 'acc_tg', 'email', 'phone')


@admin.register(Question)
class QuestionAdmin(admin.ModelAdmin):
    list_display = ('survey', 'numb', 'que_text')
    list_filter = ('survey', 'numb', 'que_text')
    search_fields = ('survey', 'numb', 'que_text')


@admin.register(Survey)
class SurveyAdmin(admin.ModelAdmin):
    prepopulated_fields = {"slug": ("name",)}
    list_display = ('name', 'description')
    list_filter = ('name', 'description')
    search_fields = ('name', 'description')


@admin.register(Mark)
class MarkAdmin(admin.ModelAdmin):
    list_display = ('mark_text', 'que',)
    list_filter = ('mark_text', 'que',)
    search_fields = ('mark_text', 'que',)