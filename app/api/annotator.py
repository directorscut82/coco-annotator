import copy
from flask_restplus import Namespace, Api, Resource, reqparse
from flask import request

from ..util import query_util
from ..util import coco_util
from ..models import *


api = Namespace('annotator', description='Annotator related operations')


@api.route('/data')
class AnnotatorData(Resource):

    def post(self):
        """
        Called when saving data from the annotator client
        """
        data = request.get_json(force=True)
        image = data.get('image')
        image_id = image.get('id')

        image_model = ImageModel.objects(id=image_id).first()

        if image_model is None:
            return {'message': 'image does not exist'}, 400

        categories = CategoryModel.objects.all()
        annotations = AnnotationModel.objects(image_id=image_id)

        annotated = False
        # Iterate every category passed in the data
        for category in data.get('categories', []):
            category_id = category.get('id')

            # Find corresponding category object in the database
            db_category = categories.filter(id=category_id).first()
            if db_category is None:
                continue

            db_category.update(set__color=category.get('color'))

            # Iterate every annotation from the data annotations
            for annotation in category.get('annotations', []):

                # Find corresponding annotation object in database
                annotation_id = annotation.get('id')
                db_annotation = annotations.filter(id=annotation_id).first()

                if db_annotation is None:
                    continue

                # Paperjs objects are complex, so they will not always be passed. Therefor we update
                # the annotation twice, checking if the paperjs exists.

                # Update annotation in database
                db_annotation.update(
                    set__metadata=annotation.get('metadata'),
                    set__color=annotation.get('color')
                )

                paperjs_object = annotation.get('compoundPath', [])

                # Update paperjs if it exists
                if len(paperjs_object) == 2:

                    width = db_annotation.width
                    height = db_annotation.height

                    # Generate coco formatted segmentation data
                    segmentation, area, bbox = coco_util.\
                        paperjs_to_coco(width, height, paperjs_object)

                    db_annotation.update(
                        set__segmentation=segmentation,
                        set__area=area,
                        set__bbox=bbox,
                        set__paper_object=paperjs_object,
                    )

                    if area > 0:
                        annotated = True

        image_model.update(
            set__metadata=image.get('metadata', {}),
            set__annotated=annotated,
            set__category_ids=image.get('category_ids', [])
        )

        return data


@api.route('/data/<int:image_id>')
class AnnotatorId(Resource):

    def get(self, image_id):
        """ Called when loading from the annotator client """
        image = ImageModel.objects(id=image_id).first()

        if image is None:
            return {'success': False}, 400

        dataset = DatasetModel.objects(id=image.dataset_id).first()
        categories = CategoryModel.objects(deleted=False).in_bulk(dataset.categories).items()

        # Get next and previous image
        images = list(ImageModel.objects(dataset_id=dataset.id, deleted=False).order_by('file_name').all())
        image_index = images.index(image)
        image_previous = None if image_index - 1 < 0 else images[image_index - 1].id
        image_next = None if image_index + 1 == len(images) else images[image_index + 1].id

        # Generate data about the image to return to client
        data = {
            'image': query_util.fix_ids(image),
            'categories': [],
            'dataset': query_util.fix_ids(dataset),
            'settings': []
        }

        data['image']['previous'] = image_previous
        data['image']['next'] = image_next

        for category in categories:
            category = query_util.fix_ids(category[1])

            category_id = category.get('id')
            annotations = AnnotationModel.objects(image_id=image_id, category_id=category_id, deleted=False).all()

            category['show'] = True
            category['visualize'] = False
            category['annotations'] = [] if annotations is None else query_util.fix_ids(annotations)
            data.get('categories').append(category)

        return data


