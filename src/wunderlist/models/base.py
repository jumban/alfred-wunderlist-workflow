from peewee import Model, SqliteDatabase, ForeignKeyField, DateField, DateTimeField, TimeField
from wunderlist.util import workflow
from copy import copy
from dateutil import parser

db = SqliteDatabase(workflow().datadir + '/wunderlist.db', threadlocals=True)

class BaseModel(Model):

	@classmethod
	def _api2model(cls, data):
		fields = copy(cls._meta.fields)

		# Map relationships, e.g. from user_id to user's
		for (field_name, field) in cls._meta.fields.iteritems():
			if field_name.endswith('_id'):
				fields[field_name[:-3]] = field
			elif isinstance(field, ForeignKeyField):
				fields[field_name + '_id'] = field

		# Map each data property to the correct field
		model_data = {}
		for (k, v) in data.iteritems():
			if k in fields:
				if isinstance(fields[k], (DateTimeField, DateField, TimeField)):
					model_data[fields[k].name] = parser.parse(v)
				else:
					model_data[fields[k].name] = v

		return model_data

	@classmethod
	def sync(cls):
		pass

	@classmethod
	def _perform_updates(cls, model_instances, update_items):
		from concurrent import futures

		# Map of id to the normalized item
		update_items = { item['id']:cls._api2model(item) for item in update_items }
		all_instances = []

		with futures.ThreadPoolExecutor(max_workers=4) as executor:
			with db.transaction():
				for instance in model_instances:
					if not instance:
						continue
					if instance.id in update_items:
						update_item = update_items[instance.id]
						all_instances.append(instance)

						# If the revision is different, sync any children, then update the db
						if instance.revision != update_item['revision']:
							executor.submit(instance._sync_children)
							cls.update(**update_item).where(cls.id == instance.id).execute()

						del update_items[instance.id]
					# The model does not exist anymore
					else:
						instance.delete_instance()

				for update_item in update_items.values():
					instance = cls.create(**update_item)
					executor.submit(instance._sync_children)
					all_instances.append(instance)

		return all_instances

	@classmethod
	def _populate_api_extras(cls, info):
		return info

	def _sync_children(self):
		pass

	class Meta:
		database = db