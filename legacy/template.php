<?php
	// LAYOUT
	$PAGE_TITLE = "Template";
	include "php/header.php";
	
	// CONFIGURATION
	$env = 'env0';
	$parentField = "parentfield";
	$request = "https://template.com/$env/users";
	$filters = array('id', 'firstname', 'lastname');
	$filtersValue = array_fill(0, count($filters), null);
	$headers = array('id', 'firstname', 'lastname', 'pos');
	
	// DISPLAY RESULTS
	include "php/mainLayout.php";
?>