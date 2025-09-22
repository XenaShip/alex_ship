from tkinter.constants import CASCADE

from django.contrib.postgres.fields import ArrayField
from django.db import models

NULLABLE = {'blank': True, 'null': True}


class Survey(models.Model):
    slug = models.SlugField(max_length=255, unique=True, verbose_name='slug')
    name = models.CharField(max_length=50, verbose_name='название опроса')
    description = models.TextField(verbose_name='описание опроса')
    active = models.BooleanField(verbose_name='активность опроса')
    counting = models.IntegerField(verbose_name='кол-во вопросов в опросе', **NULLABLE)
    hello_text = models.TextField(verbose_name='приветственный текст', **NULLABLE)

    def __str__(self):
        # Строковое отображение объекта
        return self.name

    class Meta:
        verbose_name = 'опрос'
        verbose_name_plural = 'опросы'


class Question(models.Model):
    CHOICES = (
        ('yes_or_no', 'yes_or_no'),
        ('one_of_some', 'one_of_some'),
        ('your_word', 'your_word')
    )
    KINDS = (
        ('photo', 'photo'),
        ('video', 'video'),
        ('audio', 'audio'),
        ('document', 'document')
    )
    survey = models.ForeignKey(Survey, on_delete=models.CASCADE, verbose_name='опрос')
    numb = models.IntegerField(verbose_name='номер вопроса')
    que_text = models.TextField(verbose_name='текст вопроса', **NULLABLE)
    type_q = models.CharField(max_length=100, choices=CHOICES, verbose_name='тип вопроса', **NULLABLE)
    wait_answer = models.BooleanField(verbose_name='ожидание ответа', **NULLABLE)
    file = models.FileField(upload_to='documents/', verbose_name="Файл документа", **NULLABLE)
    kind_file = models.CharField(max_length=100, choices=KINDS, verbose_name='тип вопроса', **NULLABLE)

    def __str__(self):
        return f'{self.survey}, {self.numb}, {self.que_text}'

    class Meta:
        verbose_name = 'вопрос'
        verbose_name_plural = 'вопросы'


class Client(models.Model):
    name = models.CharField(max_length=100, verbose_name='фио')
    acc_tg = models.CharField(max_length=100, verbose_name='ТГ аккаунт')
    email = models.EmailField(verbose_name='почта')
    phone = models.CharField(max_length=25, verbose_name='номер телефона')
    tg_id = models.BigIntegerField(unique=True, **NULLABLE)

    def __str__(self):
        return self.name

    class Meta:
        verbose_name = 'клиент'
        verbose_name_plural = 'клиенты'


class Answer(models.Model):
    client_tg_acc = models.CharField(max_length=100, verbose_name='ТГ аккаунт')
    que = models.ForeignKey(Question, on_delete=models.CASCADE, verbose_name='вопрос')
    ans = models.TextField(verbose_name='ответ')
    date = models.DateTimeField(auto_now_add=True, verbose_name='время ответа')
    client_id = models.ForeignKey(Client, on_delete=models.CASCADE, verbose_name='id клиента', **NULLABLE)

    def __str__(self):
        return f'{self.client_tg_acc}'


    class Meta:
        verbose_name = 'ответ'
        verbose_name_plural = 'ответы'


class Mark(models.Model):
    mark_text = models.TextField(verbose_name='текст кнопки')
    que = models.ForeignKey(Question, on_delete=models.CASCADE, verbose_name='вопрос')

    def __str__(self):
        return f'{self.mark_text}'

    class Meta:
        verbose_name = 'кнопка'
        verbose_name_plural = 'кнопки'