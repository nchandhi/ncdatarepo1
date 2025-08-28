DROP TABLE IF EXISTS [dbo].[customer];
CREATE TABLE [dbo].[customer] 
( 
[CustomerId] NVARCHAR(100) NOT NULL,
[CustomerTypeId] NVARCHAR(100) NOT NULL,
[CustomerRelationshipTypeId] NVARCHAR(100) NOT NULL,
[DateOfBirth] DATE NOT NULL,
[CustomerEstablishedDate] DATE NOT NULL,
[IsActive ] BIT NOT NULL,
[FirstName] NVARCHAR(100) NOT NULL,
[LastName] NVARCHAR(100) NOT NULL,
[Gender] NVARCHAR(100) NOT NULL,
[PrimaryPhone] NVARCHAR(100) NOT NULL,
[SecondaryPhone] NVARCHAR(100) NOT NULL,
[PrimaryEmail] NVARCHAR(100) NOT NULL,
[SecondaryEmail] NVARCHAR(100) NOT NULL,
[CreatedBy] NVARCHAR(100) NOT NULL,
[GoldLoadTimestamp] DATETIME2(6) NOT NULL
); 


DROP TABLE IF EXISTS [dbo].[customeraccount];
CREATE TABLE [dbo].[customeraccount] 
( 
[CustomerAccountId] NVARCHAR(100) NOT NULL,
[ParentAccountId] NVARCHAR(100) NOT NULL,
[CustomerAccountName] NVARCHAR(100) NOT NULL,
[CustomerId] NVARCHAR(100) NOT NULL,
[IsoCurrencyCode] NVARCHAR(100) NOT NULL,
[UpdatedBy] NVARCHAR(100) NOT NULL,
[GoldLoadTimestamp] DATETIME2(6)  NOT NULL
); 

DROP TABLE IF EXISTS [dbo].[customerrelationshiptype];
CREATE TABLE [dbo].[customerrelationshiptype] 
( 
[CustomerRelationshipTypeId] NVARCHAR(100) NOT NULL,
[CustomerRelationshipTypeName] NVARCHAR(100) NOT NULL,
[CustomerRelationshipTypeDescription] NVARCHAR(max) NOT NULL,
[GoldLoadTimestamp] DATETIME2(6) NOT NULL
); 

DROP TABLE IF EXISTS [dbo].[location];
CREATE TABLE [dbo].[location] 
( 
[LocationId] NVARCHAR(100) NOT NULL,
[CustomerId] NVARCHAR(100) NOT NULL,
[LocationName] NVARCHAR(100) NOT NULL,
[IsActive] BIT NOT NULL,
[AddressLine1] NVARCHAR(100) NOT NULL,
[AddressLine2] NVARCHAR(100) NOT NULL,
[City] NVARCHAR(100) NOT NULL,
[StateId] NVARCHAR(100) NOT NULL,
[ZipCode] NVARCHAR(100) NOT NULL,
[CountryId] NVARCHAR(100) NOT NULL,
[SubdivisionName] NVARCHAR(100) NOT NULL,
[Region] NVARCHAR(100) NOT NULL,
[Latitude] NVARCHAR(100) NOT NULL,
[Longitude] NVARCHAR(100) NOT NULL,
[Note] NVARCHAR(100) NOT NULL,
[UpdatedBy] NVARCHAR(100) NOT NULL,
[GoldLoadTimestamp] DATE NOT NULL
); 

DROP TABLE IF EXISTS [dbo].[product];
CREATE TABLE [dbo].[product] 
( 
[ProductID] NVARCHAR(100) NOT NULL,
[Name] NVARCHAR(100) NOT NULL,
[Color] NVARCHAR(100) NOT NULL,
[StandardCost] DECIMAL(10,2) NOT NULL,
[ListPrice] DECIMAL(10,2) NOT NULL,
[Size] NVARCHAR(100) NOT NULL,
[Weight] NVARCHAR(100) NOT NULL,
[CategoryID] NVARCHAR(100) NOT NULL,
[CategoryName] NVARCHAR(100) NOT NULL,
[UpdatedBy] NVARCHAR(100) NOT NULL,
[ProductName] NVARCHAR(100) NOT NULL,
[ProductDescription] NVARCHAR(100) NOT NULL,
[BrandName] NVARCHAR(100) NOT NULL,
[ProductNumber] NVARCHAR(100) NOT NULL,
[ProductModel] NVARCHAR(100) NOT NULL,
[ProductCategoryID] NVARCHAR(100) NOT NULL,
[WeightUom] NVARCHAR(100) NOT NULL,
[ProductStatus] NVARCHAR(100) NOT NULL,
[CreatedDate] NVARCHAR(100)  NULL,
[SellStartDate] NVARCHAR(100) NULL,
[SellEndDate] NVARCHAR(100) NULL,
[IsoCurrencyCode] NVARCHAR(100) NOT NULL,
[UpdatedDate] NVARCHAR(100) NULL,
[CreatedBy] NVARCHAR(100) NULL,
[GoldLoadTimestamp] DATETIME2(6) NOT NULL
); 

DROP TABLE IF EXISTS [dbo].[productcategory];
CREATE TABLE [dbo].[productcategory] 
( 
[CategoryID] NVARCHAR(100) NOT NULL,
[ParentCategoryId] NVARCHAR(100) NOT NULL,
[CategoryName] NVARCHAR(100) NOT NULL,
[CategoryDescription] NVARCHAR(100) NOT NULL,
[BrandName] NVARCHAR(100) NOT NULL,
[BrandLogoUrl] NVARCHAR(100) NOT NULL,
[IsActive] BIT NOT NULL,
[GoldLoadTimestamp] DATE NOT NULL
); 

DROP TABLE IF EXISTS [dbo].[orders];
CREATE TABLE [dbo].[orders] 
( 
[OrderId] NVARCHAR(100) NOT NULL,
[SalesChannelId] NVARCHAR(100) NOT NULL,
[OrderNumber] NVARCHAR(100) NOT NULL,
[CustomerId] NVARCHAR(100) NOT NULL,
[CustomerAccountId] NVARCHAR(100) NOT NULL,
[OrderDate] DATE NOT NULL,
[OrderStatus] NVARCHAR(100) NOT NULL,
[SubTotal] DECIMAL(10,2) NOT NULL,
[TaxAmount] DECIMAL(10,2) NOT NULL,
[OrderTotal] DECIMAL(10,2) NOT NULL,
[PaymentMethod] NVARCHAR(100) NOT NULL,
[IsoCurrencyCode] NVARCHAR(100) NOT NULL,
[CreatedBy] NVARCHAR(100) NOT NULL
); 

DROP TABLE IF EXISTS [dbo].[orderline];
CREATE TABLE [dbo].[orderline] 
( 
[OrderId] NVARCHAR(100) NOT NULL,
[OrderLineNumber] NVARCHAR(100) NOT NULL,
[ProductId] NVARCHAR(100) NOT NULL,
[ProductName] NVARCHAR(100) NOT NULL,
[Quantity] DECIMAL(10,2) NOT NULL,
[UnitPrice] DECIMAL(10,2) NOT NULL,
[LineTotal] DECIMAL(10,2) NOT NULL,
[DiscountAmount] DECIMAL(10,2) NOT NULL,
[TaxAmount] DECIMAL(10,2) NOT NULL
); 

DROP TABLE IF EXISTS [dbo].[orderpayment];
CREATE TABLE [dbo].[orderpayment] 
( 
[OrderId] NVARCHAR(100) NOT NULL,
[PaymentMethod] NVARCHAR(100) NOT NULL,
[TransactionId] NVARCHAR(100) NOT NULL
);

DROP TABLE IF EXISTS [dbo].[hst_conversation_messages];
CREATE TABLE [dbo].[hst_conversation_messages](
    [Id] [int] IDENTITY(1,1) NOT NULL,
    [userId] [nvarchar](50) NULL,
    [conversation_id] [nvarchar](50) NOT NULL,
    [role] [nvarchar](50) NULL,
    [content_id] [nvarchar](50) NULL,
    [content] [nvarchar](max) NULL,
    [citations] [nvarchar](max) NULL,
    [feedback] [nvarchar](max) NULL,
    [createdAt] [datetime2](7) NOT NULL,
    [updatedAt] [datetime2](7) NOT NULL);
 
DROP TABLE IF EXISTS [dbo].[hst_conversations]; 
CREATE TABLE [dbo].[hst_conversations](
    [Id] [int] IDENTITY(1,1) NOT NULL,
    [userId] [nvarchar](50) NULL,
    [conversation_id] [nvarchar](50) NOT NULL,
    [title] [nvarchar](255) NULL,
    [createdAt] [datetime2](7) NOT NULL,
    [updatedAt] [datetime2](7) NOT NULL);
