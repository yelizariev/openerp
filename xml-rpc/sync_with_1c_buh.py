#!/usr/bin/env python
#coding: utf-8
#Скрипт выполняет синхронизацию OpenERP с 1С Бухгалтерией
#Автор - Денис Каратаев, 2012.

#Сразу выводим тим содержимого
print 'Content-Type: text/xml'
#Запрещаем кеширование
print 'Cache-Control: no-store, no-cache,  must-revalidate'
print 'Expires: 10 Aug 2010 10:00:00 +0400'
print

import cgi, cgitb
import smtplib
from email.mime.text import MIMEText
from xmlrpclib import ServerProxy, Fault
from xml.dom.minidom import Document
from lxml import etree

#Настройки базы
server = 'http://localhost:8069/xmlrpc/'
db = 'dbname'
uname = 'admin'
pwd = 'password'
context = {'lang': 'ru_RU'}

#Правильный ключ для соединения со скриптом извне
true_skey = '35c89a88133cfbd8fbd08e83a4454b1a'

#Данные для отправки уведомлений админу
mailto = 'mail@gmail.com'
smtp_server = 'smtp.gmail.com'
smtp_password = 'password'
#Логировать ли все обмены на почту
mail_log = True

def mail(message):
    msg = MIMEText(message)
    msg['Subject'] = 'Отчет об ошибках при синхронизации OpenERP с 1С Бухгалтерией'
    msg['From'] = mailto
    msg['To'] = mailto
    smtp = smtplib.SMTP_SSL()
    smtp.connect(smtp_server)
    smtp.login(mailto, smtp_password)
    smtp.sendmail(mailto, mailto, msg.as_string())
    smtp.quit()

#Основной код
try:
    #Для работы с CGI
    cgitb.enable()
    request = cgi.FieldStorage()

    #Проверяем, есть ли полномочия у запускающего скрипт
    skey = request.getvalue('skey')
    if skey != true_skey:
        raise Exception('Неправильный секретный ключ')

    #Подключаемся к базе и получаем uid пользователя
    sock = ServerProxy(server + 'object', allow_none=True)
    sock_common = ServerProxy(server + 'common')
    uid = sock_common.login(db, uname, pwd)

    #Проверяем, был ли послан файл
    if 'userfile' in request:
        userfile = request['userfile']
        if userfile.file:
            #Парсим XML файл
            doc = etree.parse(userfile.file)
            data = doc.xpath('/data')[0]

            #Получаем ответы о синхронизации продуктов
            info = ''.join((u'Журнал синхронизации с бухгалтерией ', data.get('title'), ':\r\n'))
            errors = u'При синхронизации OpenERP с 1С Бухгалтерией произошли следующие ошибки:\r\n'
            is_errors = False
            products = doc.xpath('/data/products/product')
            for product in products:
                if mail_log:
                    info = '\r\n'.join((info, u'Продукт %s: %s %s' % (product.get('id'), product.text, product.get('id_buh'))))
                if product.text != u'Создан элемент' and product.text != u'Обновлен элемент':
                    is_errors = True
                    errors = '\r\n'.join((errors, u'Продукт %s: %s %s' % (product.get('id'), product.text,
                                                                                            u'(Ошибка на стороне 1С)')))
            if mail_log:
                mail(info.encode('UTF-8'))
            #Если имеются ошибки, высылаем письмо админу
            if is_errors:
                mail(errors.encode('UTF-8'))
            doc = Document()
            xmlAnswer = doc.createElement('answer')
            xmlAnswerText = doc.createTextNode('ok')
            xmlAnswer.appendChild(xmlAnswerText)
            doc.appendChild(xmlAnswer)
            print doc.toprettyxml(indent='  ', encoding='UTF-8')
    else:
        #Файл нам не прислали, значит будем мы данные выводить для новой синхронизации
        doc = Document()
        xmlData = doc.createElement('data')
        doc.appendChild(xmlData)
        xmlProducts = doc.createElement('products')
        xmlData.appendChild(xmlProducts)

        product_ids = sock.execute(db, uid, pwd, 'product.product', 'search', [], 0, None, None, context)

        fields = ['id', 'name', 'taxes_id', 'uom_id']
        products = sock.execute(db, uid, pwd, 'product.product', 'read', product_ids, fields, context)
        for product in products:
            xmlProduct = doc.createElement('product')
            xmlProduct.setAttribute('id', str(product['id']))

            xmlProductName = doc.createElement('name')
            xmlProductNameText = doc.createTextNode(product['name'])
            xmlProductName.appendChild(xmlProductNameText)
            xmlProduct.appendChild(xmlProductName)

            vat = 0
            fields = ['amount', 'description']
            taxes = sock.execute(db, uid, pwd, 'account.tax', 'read', product['taxes_id'], fields, context)
            for tax in taxes:
                if tax['description'] == 'vat':
                    vat = int(tax['amount'] * 100)
                    break
            if not vat:
                raise Exception(' '.join(('Укажите ставку НДС у товара', product['name'].encode('UTF-8'))))
            xmlProductVat = doc.createElement('vat')
            xmlProductVatText = doc.createTextNode(str(vat))
            xmlProductVat.appendChild(xmlProductVatText)
            xmlProduct.appendChild(xmlProductVat)

            xmlProductUom = doc.createElement('uom')
            xmlProductUomText = doc.createTextNode(product['uom_id'][1])
            xmlProductUom.appendChild(xmlProductUomText)
            xmlProduct.appendChild(xmlProductUom)

            xmlProducts.appendChild(xmlProduct)

        xmlPartners = doc.createElement('partners')
        xmlData.appendChild(xmlPartners)

        partner_ids = sock.execute(db, uid, pwd, 'res.partner', 'search', [], 0, None, None, context)

        fields = ['id', 'name', 'name_official', 'inn', 'kpp', 'okpo', 'contract_num', 'contract_date',
                  'supplier', 'customer']
        partners = sock.execute(db, uid, pwd, 'res.partner', 'read', partner_ids, fields, context)
        for partner in partners:
            xmlPartner = doc.createElement('partner')
            xmlPartner.setAttribute('id', str(partner['id']))

            if partner['supplier']:
                xmlPartner.setAttribute('supplier', '1')
            else:
                xmlPartner.setAttribute('customer', '1')

            xmlPartnerName = doc.createElement('name')
            xmlPartnerNameText = doc.createTextNode(partner['name'] or '')
            xmlPartnerName.appendChild(xmlPartnerNameText)
            xmlPartner.appendChild(xmlPartnerName)

            xmlPartnerNameOfficial = doc.createElement('name_official')
            xmlPartnerNameOfficialText = doc.createTextNode(partner['name_official'] or '')
            xmlPartnerNameOfficial.appendChild(xmlPartnerNameOfficialText)
            xmlPartner.appendChild(xmlPartnerNameOfficial)

            xmlPartnerInn = doc.createElement('inn')
            xmlPartnerInnText = doc.createTextNode(partner['inn'] or '')
            xmlPartnerInn.appendChild(xmlPartnerInnText)
            xmlPartner.appendChild(xmlPartnerInn)

            xmlPartnerKpp = doc.createElement('kpp')
            xmlPartnerKppText = doc.createTextNode(partner['kpp'] or '')
            xmlPartnerKpp.appendChild(xmlPartnerKppText)
            xmlPartner.appendChild(xmlPartnerKpp)

            xmlPartnerOkpo = doc.createElement('okpo')
            xmlPartnerOkpoText = doc.createTextNode(partner['okpo'] or '')
            xmlPartnerOkpo.appendChild(xmlPartnerOkpoText)
            xmlPartner.appendChild(xmlPartnerOkpo)

            xmlPartnerContractNum = doc.createElement('contract_num')
            xmlPartnerContractNumText = doc.createTextNode(partner['contract_num'] or '')
            xmlPartnerContractNum.appendChild(xmlPartnerContractNumText)
            xmlPartner.appendChild(xmlPartnerContractNum)

            xmlPartnerContractDate = doc.createElement('contract_date')
            xmlPartnerContractDateText = doc.createTextNode(partner['contract_date']
                                                            and partner['contract_date'].replace('-', '') or '')
            xmlPartnerContractDate.appendChild(xmlPartnerContractDateText)
            xmlPartner.appendChild(xmlPartnerContractDate)

            fields = ['id', 'type', 'zip', 'country_id', 'state_id', 'city', 'street', 'phone']
            partner_address_default_ids = sock.execute(db, uid, pwd, 'res.partner.address', 'search',
                                [('partner_id', '=', partner['id']), ('type', '=', 'default')], 0, None, None, context)
            partner_address_actual_ids = sock.execute(db, uid, pwd, 'res.partner.address', 'search',
                                [('partner_id', '=', partner['id']), ('type', '=', 'actual')], 0, None, None, context)
            if partner_address_default_ids:
                partner_address_default_id = partner_address_default_ids[0]
                partner_address_default = sock.execute(db, uid, pwd, 'res.partner.address', 'read',
                                                       partner_address_default_id, fields, context)
                partner_address_default_str = partner_address_default['zip'] or ''
                if partner_address_default['country_id']:
                    if partner_address_default_str:
                        partner_address_default_str = ', '.join((partner_address_default_str, partner_address_default['country_id'][1]))
                    else:
                        partner_address_default_str = partner_address_default['country_id'][1]
                if partner_address_default['state_id']:
                    if partner_address_default_str:
                        partner_address_default_str = ', '.join((partner_address_default_str, partner_address_default['state_id'][1]))
                    else:
                        partner_address_default_str = partner_address_default['state_id'][1]
                if partner_address_default['city']:
                    if partner_address_default_str:
                        partner_address_default_str = ', '.join((partner_address_default_str, partner_address_default['city']))
                    else:
                        partner_address_default_str = partner_address_default['city']
                if partner_address_default['street']:
                    if partner_address_default_str:
                        partner_address_default_str = ', '.join((partner_address_default_str, partner_address_default['street']))
                    else:
                        partner_address_default_str = partner_address_default['street']
            else:
                partner_address_default_str = ''
            xmlPartnerAddressDefault = doc.createElement('address_default')
            xmlPartnerAddressDefaultText = doc.createTextNode(partner_address_default_str)
            xmlPartnerAddressDefault.appendChild(xmlPartnerAddressDefaultText)
            xmlPartner.appendChild(xmlPartnerAddressDefault)

            if partner_address_actual_ids:
                partner_address_actual_id = partner_address_actual_ids[0]
                partner_address_actual = sock.execute(db, uid, pwd, 'res.partner.address', 'read',
                    partner_address_actual_id, fields, context)
                partner_address_actual_str = partner_address_actual['zip'] or ''
                if partner_address_actual['country_id']:
                    if partner_address_actual_str:
                        partner_address_actual_str = ', '.join((partner_address_actual_str, partner_address_actual['country_id'][1]))
                    else:
                        partner_address_actual_str = partner_address_actual['country_id'][1]
                if partner_address_actual['state_id']:
                    if partner_address_actual_str:
                        partner_address_actual_str = ', '.join((partner_address_actual_str, partner_address_actual['state_id'][1]))
                    else:
                        partner_address_actual_str = partner_address_actual['state_id'][1]
                if partner_address_actual['city']:
                    if partner_address_actual_str:
                        partner_address_actual_str = ', '.join((partner_address_actual_str, partner_address_actual['city']))
                    else:
                        partner_address_actual_str = partner_address_actual['city']
                if partner_address_actual['street']:
                    if partner_address_actual_str:
                        partner_address_actual_str = ', '.join((partner_address_actual_str, partner_address_actual['street']))
                    else:
                        partner_address_actual_str = partner_address_actual['street']
            else:
                partner_address_actual_str = ''
            xmlPartnerAddressActual = doc.createElement('address_actual')
            xmlPartnerAddressActualText = doc.createTextNode(partner_address_actual_str)
            xmlPartnerAddressActual.appendChild(xmlPartnerAddressActualText)
            xmlPartner.appendChild(xmlPartnerAddressActual)

            partner_phone = ''
            if partner_address_default_ids and partner_address_default['phone']:
                partner_phone = partner_address_default['phone']
            elif partner_address_actual_ids and partner_address_actual['phone']:
                partner_phone = partner_address_actual['phone']
            xmlPartnerPhone = doc.createElement('phone')
            xmlPartnerPhoneText = doc.createTextNode(partner_phone)
            xmlPartnerPhone.appendChild(xmlPartnerPhoneText)
            xmlPartner.appendChild(xmlPartnerPhone)

            partner_bank_account_ids = sock.execute(db, uid, pwd, 'res.partner.bank', 'search',
                                                        [('partner_id', '=', partner['id'])], 0, None, None, context)
            if partner_bank_account_ids:
                xmlPartnerBankAccounts = doc.createElement('bank_accounts')
                xmlPartner.appendChild(xmlPartnerBankAccounts)
                fields = ['id', 'acc_number', 'owner_name', 'bank_name', 'bank_bic', 'bank_acc_corr']
                partner_bank_accounts = sock.execute(db, uid, pwd, 'res.partner.bank', 'read',
                                                                            partner_bank_account_ids, fields, context)
                for partner_bank_account in partner_bank_accounts:
                    xmlPartnerBankAccount = doc.createElement('account')
                    xmlPartnerBankAccounts.appendChild(xmlPartnerBankAccount)

                    xmlPartnerBankAccountNumber = doc.createElement('number')
                    xmlPartnerBankAccountNumberText = doc.createTextNode(partner_bank_account['acc_number'])
                    xmlPartnerBankAccountNumber.appendChild(xmlPartnerBankAccountNumberText)
                    xmlPartnerBankAccount.appendChild(xmlPartnerBankAccountNumber)

                    xmlPartnerBankAccountBank = doc.createElement('bank')
                    xmlPartnerBankAccount.appendChild(xmlPartnerBankAccountBank)

                    xmlPartnerBankAccountBankName = doc.createElement('namebank')
                    xmlPartnerBankAccountBankNameText = doc.createTextNode(partner_bank_account['bank_name'])
                    xmlPartnerBankAccountBankName.appendChild(xmlPartnerBankAccountBankNameText)
                    xmlPartnerBankAccountBank.appendChild(xmlPartnerBankAccountBankName)

                    xmlPartnerBankAccountBankBic = doc.createElement('bic')
                    xmlPartnerBankAccountBankBicText = doc.createTextNode(partner_bank_account['bank_bic'])
                    xmlPartnerBankAccountBankBic.appendChild(xmlPartnerBankAccountBankBicText)
                    xmlPartnerBankAccountBank.appendChild(xmlPartnerBankAccountBankBic)

                    xmlPartnerBankAccountBankAccCorr = doc.createElement('acc_corr')
                    xmlPartnerBankAccountBankAccCorrText = doc.createTextNode(partner_bank_account['bank_acc_corr'])
                    xmlPartnerBankAccountBankAccCorr.appendChild(xmlPartnerBankAccountBankAccCorrText)
                    xmlPartnerBankAccountBank.appendChild(xmlPartnerBankAccountBankAccCorr)

            xmlPartners.appendChild(xmlPartner)

        print doc.toprettyxml(indent='  ', encoding='UTF-8')
except Exception,e:
    if isinstance(e, Fault):
        error_message = e.faultCode.encode('UTF-8')
    else:
        error_message = e.message
    mail(' '.join((error_message, '(OpenERP)')))
    print '<error>%s</error>' % error_message