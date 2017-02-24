from fields import Field, PkField, ManyToMany
from manager import ModelManager

from exceptions import ModelError, FieldError
from log import logger

__all__ = ['Model', ]


class ModelMeta(type):

    def __new__(cls, clsname, bases, clsdict):
        base_class = super().__new__(cls, clsname, bases, clsdict)

        base_class.objects = type(
            "{}Manager".format(base_class.__name__),
            (ModelManager, ),
            {"model": base_class}
        )()

        return base_class


class BaseModel(object, metaclass=ModelMeta):
    table_name = ''

    objects = None

    def __init__(self, **kwargs):
        logger.debug('initiating model {}'.format(self.__class__.__name__))
        # test done
        self.objects.model = self.__class__

        if not self.table_name:
            self.table_name = self.__class__.__name__.lower()
            self.__class__.table_name = self.table_name

        manager = getattr(self, 'objects')
        manager.model = self.__class__

        self.fields, self.field_names, pk_needed = self._get_fields()

        if pk_needed:
            self.__class__.id = PkField()
            setattr(self.__class__.id, 'orm_field_name', 'id')
            self.fk_field = self.__class__.id

            self.fields = [self.id] + self.fields
            self.field_names = ['id'] + self.field_names
        else:
            pk_fields = [f for f in self.fields if isinstance(f, PkField)]
            self.fk_field = pk_fields[0]

        self._validate_kwargs(kwargs)

        for field_name in self.field_names:
            setattr(
                self,
                field_name,
                kwargs.get(
                    field_name,
                    getattr(self.__class__, field_name).default
                )
            )

        self.kwargs = kwargs
        logger.debug('... initiated')

    @classmethod
    def _get_fields(cls):
        # test done
        fields = []
        field_names = []

        attr_names = []
        for f in cls.__dict__.keys():
            field = getattr(cls, f)
            if isinstance(field, Field):
                field.orm_field_name = f

                if not field.field_name:
                    field._set_field_name(f)

                if not field.table_name:
                    field.table_name = cls.table_name

                if isinstance(field, ManyToMany):
                    setattr(field, 'foreign_model', cls.table_name)
                    setattr(field, 'table_name',
                        '{my_model}_{foreign_key}'.format(
                            my_model=cls.table_name,
                            foreign_key=field.field_name,

                        )
                    )

                fields.append(field)
                field_names.append(f)
                attr_names.append(field.field_name)

        if len(attr_names) != len(set(attr_names)):
            raise ModelError(
                'Models should have unique attribute names and '
                'field_name if explicitly edited!'
            )

        pk_needed = False
        if PkField not in [f.__class__ for f in fields]:
            pk_needed = True

        return fields, field_names, pk_needed

    def _validate_kwargs(self, kwargs):
        '''validate the kwargs on object instantiation only'''
        # test done
        attr_errors = [k for k in kwargs.keys() if k not in self.field_names]

        if attr_errors:
            err_string = '"{}" is not an attribute for {}'
            error_list = [
                err_string.format(k, self.__class__.__name__)
                for k in attr_errors
            ]
            raise ModelError(error_list)

        for k, v in kwargs.items():
            att_class = getattr(self.__class__, k).__class__
            att_class._validate(v)
            if att_class is PkField and v:
                raise FieldError('Models can not be generated with forced id')

    @property
    def _fk_db_fieldname(self):
        '''model foreign_key database fieldname'''
        return self.fk_field.field_name

    @property
    def _fk_orm_fieldname(self):
        '''model foreign_key orm fieldname'''
        return self.fk_field.orm_field_name

    def _creation_query(self):
        constraints = self._get_field_constraints()

        query = (
            'CREATE TABLE {table_name} ({field_queries});{constraints}{ending}'
        ).format(
            table_name=self.table_name,
            field_queries=self._get_field_queries(),
            constraints=constraints,
            ending=constraints and ';' or '',
        )
        return query

    def _get_field_queries(self):
        # builds the table with all its fields definition
        return ', '.join([f._creation_query() for f in self.fields
            if not isinstance(f, ManyToMany)])

    def _get_field_constraints(self):
        # builds the table with all its fields definition
        return '; '.join([f._field_constraints() for f in self.fields])

    def _get_m2m_field_queries(self):
        # builds the relational 1_to_1 table
        return '; '.join([f._creation_query() for f in self.fields
            if isinstance(f, ManyToMany)]
            )

    def _create_save_string(self, fields, field_data):
        interpolate = ','.join(['{}'] * len(fields))
        save_string = '''
            INSERT INTO {table_name} ({interpolate}) VALUES ({interpolate});
        '''.format(
            table_name=self.__class__.table_name,
            interpolate=interpolate,
        )
        save_string = save_string.format(*tuple(fields + field_data))
        return save_string

    def _update_save_string(self, fields, field_data):
        interpolate = ','.join(['{}'] * len(fields))
        save_string = '''
            UPDATE ONLY {table_name} SET ({interpolate}) VALUES ({interpolate})
            WHERE {_fk_db_fieldname}={model_id};
        '''.format(
            table_name=self.__class__.table_name,
            interpolate=interpolate,
            _fk_db_fieldname=self._fk_db_fieldname,
            model_id=getattr(self, self._fk_orm_fieldname)
        )
        save_string = save_string.format(*tuple(fields + field_data))
        return save_string

    def _db_save(self):
        # performs the database save
        fields, field_data = [], []
        for k, data in self.kwargs.items():
            f_class = getattr(self.__class__, k)

            # we add the field_name in db
            fields.append(f_class.field_name or k)
            field_data.append(f_class._sanitize_data(data))

        self._update_save_string(fields, field_data)
        if getattr(self, self._fk_db_fieldname):
            return self._update_save_string(fields, field_data)
        return self._create_save_string(fields, field_data)

    def __str__(self):
        return '< {} object >'.format(self.__class__.__name__)

    def __repr__(self):
        return '< {} object >'.format(self.__class__.__name__)


class Model(BaseModel):

    def _construct(self, data):
        # poblates the model with the data
        for k, v in data.items():
            setattr(self, k, v)
        return self

    def save(self):
        self.objects.save()

    def delete(self):
        self.objects.save()
