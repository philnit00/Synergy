# -*- coding: utf-8 -*-
import itertools

from django import forms
from django.forms import models as model_forms
from django.db.models import get_model
from django.utils.datastructures import SortedDict
from models import get_parent_field

def create_m2m_form_factory(rel, from_model):
    to_exclude = [from_model._meta.object_name.lower()]

    class M2MBaseForm(forms.ModelForm):
        def __init__(self, select, instance=None, *args, **kwargs):
            super(M2MBaseForm, self).__init__(instance=instance, *args, **kwargs)

            r_name = rel.through._meta.object_name.lower()
            self.select = select
            self.fields[r_name].initial = select.id
            self.fields[r_name].widget = forms.widgets.HiddenInput()
            self.fields["%s_%d" % (select._meta.object_name.lower(), select.id)] = forms.BooleanField(label=select, required=False, initial=bool(instance))

        def save(self, *args, **kwargs):
            return super(M2MBaseForm, self).save(*args, **kwargs)

        class Meta:
            model =  rel.through
            exclude = to_exclude

    return M2MBaseForm

def createform_factory(created_model, related_models, excluded_fields=[]):

    to_exclude = excluded_fields + map(lambda x: str(x.name), created_model._meta.many_to_many)

    class CreateBaseForm(forms.ModelForm):
        def __init__(self, instance=None, parent=None, *args, **kwargs):
            super(CreateBaseForm, self).__init__(instance=instance, *args, **kwargs)

            self.external = SortedDict()
            if parent:
                parent_field = get_parent_field(self.instance._meta)
                self.fields[parent_field.name].initial = parent.id
                self.fields[parent_field.name].widget = forms.widgets.HiddenInput()
                
            categorical_model = get_model('records', 'CategoricalValue')

            for field in self._meta.model._meta.fields:
                if field.rel and field.rel.to is categorical_model:
                    # Jeżeli pole jest relacją do CategoricalValue, to dozwolone wartości 
                    # muszą należeć do grupy o tej nazwie pola
                    self.fields[field.name].queryset = self.fields[field.name].queryset.filter(group__name=field.name)

            for related_model in related_models:
                self.external[related_model] = []
                for i in range(related_model.elements_count):
                    ins = None
                    if not self.instance.pk is None:
                        ins = related_model.model.model_class().objects.filter(**{related_model.setup.model.model: self.instance})[i]
                    prefix="%s_%d" % (related_model.model.model, i)
                    df = createform_factory(related_model.model.model_class(), [], excluded_fields=[self._meta.model._meta.object_name.lower()])(instance=ins, 
                                                                                                                                                 prefix=prefix,
                                                                                                                                                 *args, **kwargs)
                    self.external[related_model].append(df)

            self.external_m2m = {}
            for related_m2m_model in created_model._meta.many_to_many:
                self.external_m2m[related_m2m_model] = []
                choice_manager  = related_m2m_model.rel.to._default_manager
                if choice_manager.model is categorical_model:
                    choices = choice_manager.filter(group__name=related_m2m_model.rel.through._meta.object_name.lower())
                else:
                    choices = choice_manager.all()
                for choice in choices:
                    ins = None
                    if not self.instance.pk is None:
                        try:
                            ins = related_m2m_model.rel.through._default_manager.get(**{related_m2m_model.model._meta.object_name.lower(): self.instance,
                                                                                        related_m2m_model.rel.through._meta.object_name.lower(): choice})
                        except related_m2m_model.rel.through.DoesNotExist:
                            ins = None

                    prefix="%s_%d" % (related_m2m_model.model._meta.object_name.lower(), choice.id)
                    self.external_m2m[related_m2m_model].append(create_m2m_form_factory(related_m2m_model.rel, related_m2m_model.model)(instance=ins, select=choice, 
                                                                                                                                        prefix=prefix, *args, **kwargs))
                

        def is_valid(self):
            valid = [super(CreateBaseForm, self).is_valid()]
            for ex in itertools.chain(*self.external.values()):
                valid.append(ex.is_valid())

            for f in itertools.chain(*self.external_m2m.values()):
                valid.append(f.is_valid())
            return all(valid)

        def save(self, *args, **kwargs):
            self.instance = super(CreateBaseForm, self).save(*args, **kwargs)

            for f in itertools.chain(*self.external.values()):
                ins = f.save(commit=False)
                setattr(ins, self._meta.model._meta.object_name.lower(), self.instance)
                ins.save()

            for f in itertools.chain(*self.external_m2m.values()):
                if f.cleaned_data["%s_%d" % (f.select._meta.object_name.lower(), f.select.id)]:
                    ins = f.save(commit=False)
                    setattr(ins, self._meta.model._meta.object_name.lower(), self.instance)
                    ins.save()
                else:
                    if not f.instance.pk is None:
                        f.instance.delete()

            return self.instance

        class Meta:
            model =  created_model
            exclude = to_exclude

    return CreateBaseForm
