-- DB.sql (новая схема таблиц)
create table suppliers(
    supp_id serial primary key,
    supp_name varchar(255)
);

create table pickup_points(
    pp_id serial primary key,
    pp_name varchar(255)
);

create table categories(
    categ_id serial primary key,
    categ_name varchar(255)
);

create table statuses(
    status_id serial primary key,
    status_name varchar(255)
);

create table users(
    user_id serial primary key,
    user_role varchar(255),
    user_name varchar(255),
    user_login varchar(255),
    user_password varchar(255)
);

create table products(
    product_id serial primary key,
    product_art  varchar(255),
    product_name  varchar(255),
    product_unit varchar(255),
    product_price numeric(10,2) check(product_price >= 0),
    supp_id integer,
    product_manufac varchar(255),
    categ_id integer,
    product_discount integer check (product_discount>= 0 and product_discount <= 100),
    product_stock integer,
    product_desc  varchar(255),
    product_photo  varchar(255),
    foreign key(supp_id) references suppliers(supp_id) on delete restrict,
    foreign key(categ_id) references categories(categ_id) on delete restrict
);

create table orders (
    order_id serial primary key,
    order_date date,
    order_pup_date date,
    pp_id integer,
    user_name varchar(255),
    order_pp_code integer,
    status_id integer,
    foreign key(pp_id) references pickup_points(pp_id)  on delete restrict,
    foreign key(status_id) references statuses(status_id)  on delete restrict
);

create table order_items(
    order_item_id serial primary key,
    order_id integer,
    product_id integer,
    product_quantity integer check(product_quantity > 0),
    foreign key(order_id) references orders(order_id)  on delete restrict,
    foreign key(product_id) references products(product_id)  on delete restrict
);
