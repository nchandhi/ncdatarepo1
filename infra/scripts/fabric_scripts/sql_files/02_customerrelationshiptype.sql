DROP TABLE IF EXISTS [dbo].[customerrelationshiptype];
CREATE TABLE [dbo].[customerrelationshiptype] 
( 
[CustomerRelationshipTypeId] NVARCHAR(100) NOT NULL,
[CustomerRelationshipTypeName] NVARCHAR(100) NOT NULL,
[CustomerRelationshipTypeDescription] NVARCHAR(max) NOT NULL,
[GoldLoadTimestamp] DATETIME2(6) NOT NULL
); 
INSERT INTO [dbo].[customerrelationshiptype] ([CustomerRelationshipTypeId], [CustomerRelationshipTypeName], [CustomerRelationshipTypeDescription], [GoldLoadTimestamp]) 
    VALUES ('Standard', 'Standard Individual', 'Basic individual customer with standard service level and pricing. Entry-level tier for personal customers.', '2025-08-07 17:40:22.259184'),
('Premium', 'Premium Individual', 'Enhanced individual customer with priority support, exclusive offers, and premium service benefits.', '2025-08-07 17:40:22.259184'),
('VIP', 'VIP Individual', 'Top-tier individual customer with white-glove service, dedicated support, and exclusive access to premium products and events.', '2025-08-07 17:40:22.259184'),
('SMB', 'Small-Medium Business', 'Small to medium-sized business customers with volume discounts, business support, and flexible payment terms.', '2025-08-07 17:40:22.259184'),
('Premier', 'Premier Business', 'High-value business customers with dedicated account management, priority support, and customized solutions.', '2025-08-07 17:40:22.259184'),
('Partner', 'Strategic Partner', 'Strategic business partners including resellers, distributors, and channel partners with special pricing and co-marketing opportunities.', '2025-08-07 17:40:22.259184'),
('Local', 'Local Government', 'Local government entities including cities, counties, municipalities, and local agencies with government pricing and procurement support.', '2025-08-07 17:40:22.259184'),
('State', 'State Government', 'State government departments and agencies with enterprise-level support, compliance assistance, and state contract pricing.', '2025-08-07 17:40:22.259184'),
('Federal', 'Federal Government', 'Federal government agencies and departments with specialized compliance support, GSA pricing, and security clearance requirements.', '2025-08-07 17:40:22.259184')
