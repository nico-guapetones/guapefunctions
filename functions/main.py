# Welcome to Cloud Functions for Firebase for Python!
# To get started, simply uncomment the below code or create your own.
# Deploy with `firebase deploy`
# from firebase_functions import logger
import json
import datetime

from firebase_functions import https_fn, options
from firebase_admin import initialize_app, firestore, messaging, auth
#from firebase_tools import firestore

from firebase_functions.firestore_fn import (
    on_document_created,
    on_document_deleted,
    on_document_updated,
    on_document_written,
    Event,
    Change,
    DocumentSnapshot,
)

import google.cloud.firestore
from google.cloud.firestore_v1 import DocumentReference

initialize_app()


@https_fn.on_request(cors=options.CorsOptions(cors_origins="*", cors_methods=["post"]))
def convert_userid_or_email(req: https_fn.Request) -> https_fn.Response: 

    decoded_token = auth.verify_id_token(req.authorization.token)
    uid = decoded_token['uid']

    user = auth.get_user(uid)

    firestore_client: google.cloud.firestore.Client = firestore.client()

    # Is admin
    if firestore_client.document(f"admins/{user.uid}").get().exists:
        request = json.loads(req.data)

        keys = list(request.keys())

        response = '';

        match keys[0]:
            case 'userId':
                userAuth = auth.get_user(request['userId'])
                response = userAuth.email

            case 'email':
                userAuth = auth.get_user_by_email(request['email'])
                response = userAuth.uid
                
        return https_fn.Response(response)
    
    #Not admin
    else:
        return https_fn.Response("", 403)

@https_fn.on_request(cors=options.CorsOptions(cors_origins="*", cors_methods=["get", "post"]))
def fix_pet_accessory_relation(req: https_fn.Request) -> https_fn.Response:
    firestore_client: google.cloud.firestore.Client = firestore.client()

    startTime = datetime.datetime.now()
    print('BEGINING')

    for family in firestore_client.collection("family").get():

        print(f"Family: {family.id}")

        for pet in firestore_client.collection(f"family/{family.id}/pet").get():

            print(f"Pet: {pet.id}")

            for accesory in pet._data.get('accessories'):

                petData = pet._data
                petData['id'] = pet.id

                docRef = firestore_client.document(f"publicAccessory/{accesory}")

                if docRef.get().exists:
                    docRef.update({
                        'petData': petData
                    })

    print(f'DONE PROCESSING IN {datetime.datetime.now() - startTime}')

    return https_fn.Response("END")

@on_document_updated(document="family/{familyId}/pet/{petId}")
def on_pet_update(event: Event[Change[DocumentSnapshot]]) -> None:
    firestore_client: google.cloud.firestore.Client = firestore.client()

    new_value = event.data.after

    pet_data = new_value.to_dict()
    pet_data['id'] = event.data.after.id

    for accessory in new_value.to_dict().get("accessories"):
        firestore_client.document("publicAccessory/{}".format(accessory)).update({
            'petData': pet_data,
        })
        
# Nueva version, sale con la version 2 de la app
# @on_document_updated(document="family/{familyId}/pet/{petId}")
# def on_pet_update(event: Event[Change[DocumentSnapshot]]) -> None:
#     firestore_client: google.cloud.firestore.Client = firestore.client()
#     new_value = event.data.after
#
#     if new_value.get('creationCompleted'):
#         for accessory_id in new_value.get('accessories'):
#             public_data = {
#                 'id': accessory_id,
#                 'petData': new_value.to_dict()
#             }
#             firestore_client.document('publicAccessory/{}'.format(public_data.get('id'))).update(
#                 public_data
#             )


@on_document_deleted(document="family/{familyId}/pet/{petId}")
def on_pet_delete(event: Event[DocumentSnapshot]) -> None:
    # TODO: Sin testear
    firestore_client: google.cloud.firestore.Client = firestore.client()

    for accessory in event.data.get('accessories'):
        #firestore_client.document('publicAccessory/{}'.format(accessory)).delete()
        public_data = {
            'pet': {}
        }
        firestore_client.document('publicAccessory/{}'.format(accessory.id)).update(
            public_data
        )


@on_document_updated(document="userData/{userId}")
def on_user_data_update(event: Event[Change[DocumentSnapshot]]) -> None:
    firestore_client: google.cloud.firestore.Client = firestore.client()

    new_value = event.data.after
    print(new_value)

    for accessory in firestore_client.collection('family/{}/accessory'.format(new_value.get('familyId'))).get():
        print(accessory)
        contacts = []

        contact_data = {'userName': new_value.get('userName'),
                        'phone': "{}{}".format(new_value.get('countryCode'),
                                               new_value.get('phoneNumber'))}

        contacts.append(contact_data)

        print(contacts)
        public_data = {
            'id': accessory.get('id'),
            'familyId': new_value.get('familyId'),
            'contacts': contacts
        }

        firestore_client.document('publicAccessory/{}'.format(accessory.get('id'))).update(
            public_data
        )


@on_document_deleted(document="family/{familyId}/accessory/{accessoryId}")
def on_accessory_delete(event: Event[DocumentSnapshot]) -> None:
    firestore_client: google.cloud.firestore.Client = firestore.client()
    firestore_client.document('publicAccessory/{}'.format(event.data.get('id'))).delete()


@on_document_created(document="family/{familyId}/accessory/{accessoryId}")
def on_accessory_create(event: Event[DocumentSnapshot]) -> None:
    firestore_client: google.cloud.firestore.Client = firestore.client()

    path = event.data.reference.path
    family_id = path.split('/')[1]

    accessory_id = event.data.get('id')

    contacts = []

    for user in firestore_client.collection('family/{}/users'.format(family_id)).get():
        user_data = firestore_client.document('userData/{}'.format(user.id)).get()
        contact_data = {'userName': user_data.get('userName'),
                        'phone': "{}{}".format(user_data.get('countryCode'), user_data.get('phoneNumber'))}
        contacts.append(contact_data)

    public_data = {
        'id': accessory_id,
        'familyId': family_id,
        'contacts': contacts
    }

    firestore_client.document('publicAccessory/{}'.format(accessory_id)).set(
        public_data
    )


@on_document_created(document="geoLocations/{accessory_id}/scans/{scan_id}")
def on_scan_accessory_notification(event: Event[DocumentSnapshot]):
    firestore_client: google.cloud.firestore.Client = firestore.client()

    accessory_id = event.data.get('accessoryId')

    public_accessory = firestore_client.document('publicAccessory/{}'.format(accessory_id)).get()

    pet_id = public_accessory.get('petData').get('id')

    for user in firestore_client.collection('family/{}/users'.format(public_accessory.get('familyId'))).get():
        fcmToken = firestore_client.document('userData/{}'.format(user.id)).get().get('fcmToken')

        print(fcmToken)
        print(pet_id)
        print(f'{pet_id}')

        message = messaging.Message(
            notification=messaging.Notification(
                title='Escaneo detectado',
                body='Se ha escaneado un accesorio de {}'.format(public_accessory.get('petData').get('name')),
            ),
            token=fcmToken,
            data={'type': 'on_scan_accessory_notification', 'pet_id': pet_id}
        )
        messaging.send(message)


@https_fn.on_call()
def family_delete(req: https_fn.CallableRequest):
    firestore_client: google.cloud.firestore.Client = firestore.client()

    family_id = req.data["familyId"]
    uid = req.auth.uid
    print(uid)
    print('entro a on_family_deleted')
    print(family_id)

    def delete_collection(coll_ref, batch_size):
        if batch_size == 0:
            return

        docs = coll_ref.list_documents(page_size=batch_size)
        deleted = 0

        for doc in docs:
            print(f"Deleting doc {doc.id} => {doc.get().to_dict()}")
            doc.delete()
            deleted = deleted + 1

        if deleted >= batch_size:
            return delete_collection(coll_ref, batch_size)

    for user in firestore_client.collection("family/{familyId}/users".format(familyId=family_id)).get():
        firestore_client.document('userData/{}'.format(user.id)).delete()
        firestore_client.document('family/{familyId}/users/{userId}'.format(familyId=family_id, userId=user.id)).delete()

    delete_collection(firestore_client.collection("family/{familyId}/pet".format(familyId=family_id)), 10)

    for accessory in firestore_client.collection("family/{familyId}/accessory".format(familyId=family_id)).get():
        firestore_client.document('publicAccessory/{}'.format(accessory.id)).delete()
        delete_collection(firestore_client.collection('geoLocations/{}/scans'.format(accessory.id)), 10)
        firestore_client.document('geoLocations/{}'.format(accessory.id)).delete()

    firestore_client.document("family/{familyId}".format(familyId=family_id)).delete()

    return




# @https_fn.on_request()
# def family_delete_test(req: https_fn.CallableRequest):
#     firestore_client: google.cloud.firestore.Client = firestore.client()
#
#
#     family_id = '0WP4dZ8mIxJXyupCRIus'
#     # uid = req.auth.uid
#     # print(uid)
#     print('entro a on_family_deleted')
#     print(family_id)
#
#     def delete_collection(coll_ref, batch_size):
#         if batch_size == 0:
#             return
#
#         docs = coll_ref.list_documents(page_size=batch_size)
#         deleted = 0
#
#         for doc in docs:
#             print(f"Deleting doc {doc.id} => {doc.get().to_dict()}")
#             doc.delete()
#             deleted = deleted + 1
#
#         if deleted >= batch_size:
#             return delete_collection(coll_ref, batch_size)
#
#     for user in firestore_client.collection("family/{familyId}/users".format(familyId=family_id)).get():
#         firestore_client.document('userData/{}'.format(user.id)).delete()
#         firestore_client.document('family/{familyId}/users/{userId}'.format(familyId=family_id, userId=user.id)).delete()
#
#     delete_collection(firestore_client.collection("family/{familyId}/pet".format(familyId=family_id)), 10)
#
#     for accessory in firestore_client.collection("family/{familyId}/accessory".format(familyId=family_id)).get():
#         firestore_client.document('publicAccessory/{}'.format(accessory.id)).delete()
#         delete_collection(firestore_client.collection('geoLocations/{}/scans'.format(accessory.id)), 10)
#         firestore_client.document('geoLocations/{}'.format(accessory.id)).delete()
#
#     firestore_client.document("family/{familyId}".format(familyId=family_id)).delete()
#
#
#     return https_fn.Response("Hello world!")


# @https_fn.on_request(
#     cors=options.CorsOptions(
#         cors_origins=[r"firebase\.com$", r"https://flutter\.com"],
#         cors_methods=["get", "post"],
#     ),
# )
# def update_incomplete_public_data_from_family(req: https_fn.Request) -> https_fn.Response:
#     firestore_client: google.cloud.firestore.Client = firestore.client()
#
#     #for publicData in firestore_client.collection("publicAccessory").get():
#
#     for family in firestore_client.collection("family").get():
#
#         for pet in firestore_client.collection("family/{familyId}/pet".format(familyId=family.id)).get():
#
#             for accesory in pet._data.get('accessories'):
#
#                 p_accesory = firestore_client.document('publicAccessory/{}'.format(accesory)).get()
#
#                 if p_accesory.create_time == None:
#
#                     firestore_client.document('publicAccessory/{}'.format(accesory)).create(
#                         {
#                             'petData': pet._data
#                         }
#                     )
#
#                     user_data = firestore_client.document('userData/{}'.format(pet.get('keepers')[0])).get()
#
#                     contactData = {'userName': user_data._data.get('userName'),
#                                    'phone': "{}{}".format(user_data._data.get('countryCode'),
#                                                           user_data._data.get('phoneNumber'))}
#
#                     firestore_client.document('publicAccessory/{}'.format(accesory)).update(
#                         {
#                             'contacts': [contactData]
#                         }
#                     )
#
#                     firestore_client.document('publicAccessory/{}'.format(accesory)).update(
#                         {
#                             'familyId': user_data._data.get('familyId')
#                         }
#                     )
#
#     return https_fn.Response("Hello world!")


# @https_fn.on_request(
#     cors=options.CorsOptions(
#         cors_origins=[r"firebase\.com$", r"https://flutter\.com"],
#         cors_methods=["get", "post"],
#     ),
# )
# def update_incomplete_public_data_from_pub_acc(req: https_fn.Request) -> https_fn.Response:
#     firestore_client: google.cloud.firestore.Client = firestore.client()
#
#     for publicData in firestore_client.collection("publicAccessory").get():
#         # print(publicData.id)
#         # delete = False
#
#         if publicData._data.get('petData', None) is None:
#             print('=================================================================================================')
#             print('sin petData')
#             print(publicData._data)
#             # delete = True
#
#             for family in firestore_client.collection("family").get():
#                 for pet in firestore_client.collection("family/{familyId}/pet".format(familyId=family.id)).get():
#                     if publicData.id in pet._data.get('accessories'):
#                         print(pet._data)
#                         firestore_client.document('publicAccessory/{}'.format(publicData.id)).update(
#                             {
#                                 'petData': pet._data
#                             }
#                         )
#                         # falta escribir data
#                         # delete = False
#
#         # if delete:
#         #     print('se borra por falta de informacion: id: {}'.format(publicData.id))
#         #     firestore_client.document('publicAccessory/{}'.format(publicData.id)).delete()
#
#         if publicData._data.get('contacts', None) is None:
#             print('=================================================================================================')
#             print('sin contacts')
#             p_accesory = firestore_client.document('publicAccessory/{}'.format(publicData.id)).get()
#
#             if p_accesory:
#                 user_data = firestore_client.document(
#                     'userData/{}'.format(p_accesory.get('petData').get('keepers')[0])).get()
#                 print(user_data.__dict__)
#                 contactData = {'userName': user_data._data.get('userName'),
#                                'phone': "{}{}".format(user_data._data.get('countryCode'),
#                                                       user_data._data.get('phoneNumber'))}
#                 firestore_client.document('publicAccessory/{}'.format(publicData.id)).update(
#                     {
#                         'contacts': [contactData]
#                     }
#                 )
#
#                 firestore_client.document('publicAccessory/{}'.format(publicData.id)).update(
#                     {
#                         'familyId': user_data._data.get('familyId')
#                     }
#                 )
#
#     return https_fn.Response("Hello world!")
